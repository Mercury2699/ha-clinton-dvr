import asyncio
import logging
import struct
import time
from typing import Dict, List, Set
from aiohttp import web

_LOGGER = logging.getLogger(__name__)

class ClintonDVRHub:
    MAGIC = 0xa100

    def __init__(self, hass, host: str, port: int, username: str, password: str, stream_port: int = 8899):
        self.hass = hass
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.stream_port = stream_port

        self.seq = 0
        self.running = False
        self.reader = None
        self.writer = None

        self.camera_names: Dict[int, str] = {0: "C01", 1: "C02", 2: "C03", 3: "C04"}
        self.max_channels = 4
        self.active_channels: Set[int] = {0, 1}

        self.listeners: Dict[int, Set[asyncio.Queue]] = {}
        self.snapshots: Dict[int, bytes] = {}
        self.last_snapshot_time: Dict[int, float] = {}

        self._app = None
        self._runner = None
        self._site = None
        self._tasks: List[asyncio.Task] = []

    def make_packet(self, cmd: int, payload: bytes) -> bytes:
        total_len = len(payload) + 12
        buf = bytearray(total_len)
        struct.pack_into(">I", buf, 0, total_len - 4)
        struct.pack_into("<H", buf, 4, self.MAGIC)
        buf[6] = cmd
        buf[7] = 0x00
        buf[8] = self.seq & 0x7f
        self.seq = (self.seq + 1) & 0x7f
        buf[9] = total_len & 0xff
        buf[10] = (total_len >> 8) & 0xff
        buf[11] = (total_len >> 16) & 0xff
        buf[12:] = payload
        return bytes(buf)

    async def start(self):
        self.running = True
        self._tasks.append(self.hass.async_create_background_task(self._http_server(), "clinton_dvr_http"))
        self._tasks.append(self.hass.async_create_background_task(self._dvr_loop(), "clinton_dvr_worker"))

    async def stop(self):
        self.running = False
        for task in self._tasks:
            task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    def add_listener(self, channel: int, queue: asyncio.Queue):
        if channel not in self.listeners:
            self.listeners[channel] = set()
        self.listeners[channel].add(queue)

    def remove_listener(self, channel: int, queue: asyncio.Queue):
        if channel in self.listeners:
            self.listeners[channel].discard(queue)

    async def _http_server(self):
        self._app = web.Application()
        self._app.router.add_get("/live/{channel}", self._handle_live)
        self._app.router.add_get("/snapshot/{channel}.jpg", self._handle_snapshot)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self.stream_port)
        await self._site.start()
        _LOGGER.info("Clinton DVR stream server started on port %s", self.stream_port)

    async def _handle_live(self, request: web.Request) -> web.StreamResponse:
        try:
            channel = int(request.match_info["channel"])
        except ValueError:
            return web.Response(status=400, text="Invalid channel")

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "video/x-h264",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "close",
                "Pragma": "no-cache",
            }
        )
        await response.prepare(request)

        queue = asyncio.Queue(maxsize=150)
        self.add_listener(channel, queue)
        _LOGGER.debug("Client connected to live stream channel %s", channel)

        try:
            while self.running:
                chunk = await queue.get()
                await response.write(chunk)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self.remove_listener(channel, queue)
            _LOGGER.debug("Client disconnected from live stream channel %s", channel)

        return response

    async def _handle_snapshot(self, request: web.Request) -> web.Response:
        try:
            channel = int(request.match_info["channel"])
        except ValueError:
            return web.Response(status=400, text="Invalid channel")

        snap = await self.async_get_snapshot(channel)
        if snap:
            return web.Response(body=snap, content_type="image/jpeg")
        return web.Response(status=503, text="Snapshot unavailable")

    async def async_get_snapshot(self, channel: int) -> bytes:
        if channel in self.snapshots:
            return self.snapshots[channel]
        # Wait up to 2 seconds for a snapshot to arrive
        for _ in range(20):
            await asyncio.sleep(0.1)
            if channel in self.snapshots:
                return self.snapshots[channel]
        return b""

    async def _read_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n and self.running:
            chunk = await self.reader.read(n - len(buf))
            if not chunk:
                raise ConnectionResetError("DVR connection closed")
            buf.extend(chunk)
        return bytes(buf)

    async def _dvr_loop(self):
        while self.running:
            try:
                _LOGGER.info("Connecting to Clinton DVR at %s:%s...", self.host, self.port)
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

                # 1. Login (cmd 0x01)
                u = self.username.encode("utf-8")
                p = self.password.encode("utf-8")
                login_payload = bytearray([0x00, len(u), len(p)]) + u + p
                self.writer.write(self.make_packet(0x01, bytes(login_payload)))
                await self.writer.drain()

                # Read login response
                len_b = await self._read_exact(4)
                l = struct.unpack(">I", len_b)[0]
                resp = len_b + await self._read_exact(l)
                if resp[6] != 0x02:
                    _LOGGER.error("DVR login failed! Status cmd: %s", hex(resp[6]))
                    await asyncio.sleep(5)
                    continue
                _LOGGER.info("DVR login successful!")

                # 2. Query Camera Info (cmd 0x2e)
                self.writer.write(self.make_packet(0x2e, b""))
                await self.writer.drain()

                # 3. Start Live Stream (cmd 0x03) for all channels (mask 0x0f)
                live_payload = struct.pack("<HBB", 0x0f, 30, 0)
                self.writer.write(self.make_packet(0x03, live_payload))
                await self.writer.drain()

                # Start keepalive task
                keepalive_task = asyncio.create_task(self._keepalive_worker())

                # 4. Stream Packet Ingestion Loop
                try:
                    while self.running:
                        len_b = await self._read_exact(4)
                        plen = struct.unpack(">I", len_b)[0]
                        body = await self._read_exact(plen)
                        pkt = len_b + body
                        cmd = pkt[6]

                        if cmd == 0x29: # AV Frame
                            chan_id = pkt[14]
                            is_keyframe = bool(pkt[15] & 0x01)
                            header_len = 0x28 if (pkt[12] & 0xc0) else 0x20
                            raw_frag = pkt[header_len:]

                            # Perform 32-bit word swap
                            n_words = len(raw_frag) // 4
                            swapped = bytearray(len(raw_frag))
                            for w in range(n_words):
                                swapped[w*4:(w+1)*4] = raw_frag[w*4:(w+1)*4][::-1]

                            # Broadcast to active live stream listeners
                            if chan_id in self.listeners:
                                for q in list(self.listeners[chan_id]):
                                    try:
                                        q.put_nowait(bytes(swapped))
                                    except asyncio.QueueFull:
                                        pass

                            # Update snapshot on keyframe (scaled to 640:480 for 4:3 aspect ratio)
                            now = time.time()
                            if is_keyframe and len(swapped) > 2000:
                                if now - self.last_snapshot_time.get(chan_id, 0) > 4.0:
                                    self.last_snapshot_time[chan_id] = now
                                    asyncio.create_task(self._generate_snapshot(chan_id, bytes(swapped)))

                        elif cmd == 0x2f: # Camera Info response
                            data = pkt[12:].decode("latin1", errors="ignore")
                            for idx in range(min(self.max_channels, len(data) // 16)):
                                name = data[idx*16:(idx+1)*16].replace("\x00", "").strip()
                                if name:
                                    self.camera_names[idx] = name
                            _LOGGER.info("Discovered cameras: %s", self.camera_names)

                finally:
                    keepalive_task.cancel()

            except Exception as e:
                _LOGGER.warning("DVR connection error: %s. Reconnecting in 3s...", e)
                if self.writer:
                    try:
                        self.writer.close()
                    except Exception:
                        pass
                await asyncio.sleep(3)

    async def _keepalive_worker(self):
        while self.running:
            await asyncio.sleep(5)
            try:
                if self.writer:
                    self.writer.write(self.make_packet(0x2a, b""))
                    await self.writer.drain()
            except Exception:
                break

    async def _generate_snapshot(self, channel: int, frame_data: bytes):
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "h264", "-i", "pipe:0", "-vf", "scale=640:480", "-vframes", "1", "-f", "image2", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate(input=frame_data)
            if stdout and stdout.startswith(b"\xff\xd8"):
                self.snapshots[channel] = stdout
        except Exception as err:
            _LOGGER.debug("Snapshot generation failed for ch %s: %s", channel, err)
