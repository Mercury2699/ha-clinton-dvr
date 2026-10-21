# Clinton Electronics DVR - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

A custom Home Assistant integration that enables direct streaming and snapshot support for legacy **Clinton Electronics standalone DVRs** (such as the **Shadow Series**, CE-R4S, CE-R8S, CE-R16S, etc.) without modern RTSP support, connecting seamlessly into **Home Assistant** and **Apple HomeKit**.

---

## Background & Technical Highlights

Older Clinton Electronics analog / 960H DVRs rely on a proprietary binary streaming protocol over TCP port `7000` (Streaming Mobile Service / SMS port) used by legacy apps (such as *CEC Connect* / *AVMS*), built on Korean Astel OEM architecture (`AstelNetService`). 

These DVR units typically lack RTSP or modern web streaming endpoints, making them notoriously difficult to integrate with smart home platforms.

### Key Reverse Engineering Findings
* **Protocol Framing**: Communication runs over TCP port 7000 with custom 12-byte command framing (magic `0xa100`).
* **32-Bit Word Swap**: The DVR transmits H.264 video frames with words stored in 32-bit little-endian reversed order (`[B3, B2, B1, B0]`). This integration performs in-memory endian restoration, recovering 100% compliant standard H.264 Annex-B NAL units (`0x00000001` with SPS/PPS/IDR slices).
* **4:3 Aspect Ratio Correction**: Legacy coaxial CCTV cameras stream single-field 240p video (`704x240`), which distorts on modern 1:1 pixel displays. The integration automatically scales snapshots and streams to standard **4:3** (`640x480`).
* **Direct Passthrough**: Zero video transcoding required on your host, delivering sub-second latency and minimal CPU overhead.

---

## Features

- **Live Streaming**: Exposes standard H.264 HTTP video stream endpoints.
- **Still Snapshots**: Provides periodic and on-demand 4:3 JPEG snapshots.
- **HomeKit Ready**: Full support for Apple HomeKit with smooth live video streaming and rich preview tiles.
- **Multi-Channel**: Automatically discovers connected camera channels (e.g. C01, C02).
- **Auto Reconnect & Keepalive**: Built-in 5-second heartbeats and automatic connection recovery.

---

## Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in your Home Assistant.
2. Click the top-right three dots menu -> **Custom repositories**.
3. Enter repository URL:
   ```text
   https://github.com/Mercury2699/ha-clinton-dvr
   ```
4. Category: **Integration**.
5. Click **Add**, find **Clinton Electronics DVR**, and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Copy the `custom_components/clinton_dvr` folder into your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

Add the following to your Home Assistant `configuration.yaml`:

```yaml
clinton_dvr:
  host: "192.168.1.100"      # IP address of your Clinton DVR
  port: 7000                 # Default SMS streaming port
  username: "admin"          # Your DVR username
  password: "YOUR_PASSWORD"  # Your DVR password
  stream_port: 8899          # Local HTTP streaming port (default: 8899)
```

### Apple HomeKit Configuration Example

To expose your cameras as a dedicated HomeKit bridge with 4:3 aspect ratio correction:

```yaml
homekit:
  - name: "Clinton DVR"
    port: 21064
    pincode: "123-45-678"
    filter:
      include_entities:
        - camera.clinton_dvr_c01
        - camera.clinton_dvr_c02
    entity_config:
      camera.clinton_dvr_c01:
        video_map: "0:v:0 -vf scale=640:480"
      camera.clinton_dvr_c02:
        video_map: "0:v:0 -vf scale=640:480"
```

1. Restart Home Assistant.
2. Open the **Apple Home** app on your iPhone / iPad / Mac.
3. Tap **Add Accessory** -> **More options...**.
4. Select **Clinton DVR** and enter the 8-digit PIN code configured above.

---

## Disclaimer & Trademark Notice

* **Independent Community Project**: This project is an independent open-source integration developed strictly for local interoperability and smart home compatibility purposes. It is not an official product of, nor is it affiliated with, associated with, sponsored by, or endorsed by Clinton Electronics, Astel Co., Ltd., or any of their subsidiaries or affiliates.
* **Trademarks**: All product names, logos, trademarks, registered trademarks, and brand names (including *Clinton Electronics*, *Shadow*, *CEC Connect*, and *Astel*) mentioned in this repository are the property of their respective owners. Their use in this project is for identification and compatibility reference only, and does not imply any affiliation, sponsorship, or endorsement.
* **Warranty Disclaimer**: This software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability arising from, out of, or in connection with the software or the use or other dealings in the software.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).

