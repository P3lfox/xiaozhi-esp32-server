# Networking guide: home router or phone hotspot

How to connect the xiaozhi board to a self-hosted server running on a laptop or PC,
either on a regular home internet connection (any ISP: IPLAN, Claro, Personal, etc.)
or through a phone's mobile hotspot.

## The one rule

**The board and the server must be on the same local network.**

The board never talks to the cloud AI providers. It only talks to the server, and the
server talks to the cloud (ASR, LLM, TTS, tools) over normal HTTPS:

```
[Board] --Wi-Fi--> [Router or phone hotspot] --Wi-Fi/LAN--> [Server PC] --internet--> [Groq, DeepSeek, ElevenLabs...]
```

So the internet provider does not change the procedure. What matters is the local
network the two devices share.

## How the board finds the server

The connection happens in two steps:

| Step | Protocol | Port | What happens |
|------|----------|------|--------------|
| 1. OTA check | HTTP | 8003 | On boot the board sends a POST to the **OTA URL**. The server answers with JSON that includes the WebSocket address. |
| 2. Session | WebSocket | 8000 | The board opens a persistent two-way connection and streams Opus audio both ways. |

Two consequences:

- **The board only needs to know the OTA URL**, for example `http://192.168.1.50:8003/xiaozhi/ota/`.
- **The server fills in the WebSocket address by itself.** While `server.websocket` in the
  config still holds the default placeholder, the server detects its own LAN IP on every
  OTA request (`get_local_ip()` in `core/utils/util.py`) and sends it to the board. If you
  hardcode `server.websocket`, that auto-detection is turned off and you must keep it updated.

Where the OTA URL comes from, in priority order:

1. The **Custom OTA URL** saved in the board's setup portal (Advanced tab).
2. The URL compiled into the firmware (`CONFIG_OTA_URL`).

## Requirements on any network

- **2.4 GHz Wi-Fi.** The ESP32-S3 does not support 5 GHz.
- **Ports 8000 and 8003 open** on the server PC's firewall for the local subnet.
  With `ufw`, for example:

  ```bash
  sudo ufw allow from 192.168.0.0/16 to any port 8000,8003 proto tcp
  sudo ufw allow from 10.0.0.0/8 to any port 8000,8003 proto tcp
  sudo ufw allow from 172.16.0.0/12 to any port 8000,8003 proto tcp
  ```

  These rules cover every private address range, so they work both at home and on a hotspot.
- **The server running** before the board boots:
  `cd main/xiaozhi-server && . .venv/bin/activate && python app.py`.

To see the server PC's IP address:

```bash
ip -4 addr show wlan0     # Linux, Wi-Fi interface
```

---

## Scenario A: home internet (IPLAN, Claro, Personal, or any other ISP)

The ISP's router creates the local network and hands out addresses with DHCP. Every
ISP works the same way here. Only the subnet changes, for example `192.168.0.x`,
`192.168.1.x` or `192.168.100.x`.

### Procedure

1. **Connect the server PC** to the home Wi-Fi or plug it into the router with a cable.
2. **Find its IP**, for example `192.168.1.50`.
3. **Point the board at it.** Pick one of the two options:
   - **Firmware (permanent):** build with `CONFIG_OTA_URL` set to
     `http://192.168.1.50:8003/xiaozhi/ota/` and flash. Leave the portal's Custom OTA URL empty.
   - **Portal (no reflash):** set the Custom OTA URL in the setup portal, as in Scenario B.
4. **Join the board to the 2.4 GHz network** through the setup portal.
5. **Start the server and power the board.** The server log should show the OTA request,
   followed by the WebSocket connection.

### Recommended: reserve the PC's IP

Home routers hand out addresses with DHCP, so the PC's IP can change after a reboot.
If it changes, the board looks for the server at the old address and fails.

Fix it once by adding a **DHCP reservation** in the router's admin page. Bind the PC's
MAC address to a fixed IP. The menu is usually called "DHCP", "LAN" or "Address
reservation". Look for the router's address and login on the label on the device.

### Common problems on ISP routers

| Symptom | Cause | Fix |
|---------|-------|-----|
| The board does not see the network | 5 GHz-only network, or a combined 2.4/5 GHz name the board cannot join | Enable 2.4 GHz, or create a separate 2.4 GHz network name |
| The board connects to Wi-Fi but never reaches the server | It is on the **guest network**, or the router has **client/AP isolation** enabled | Use the main network, or turn off isolation |
| It worked yesterday, fails today | The PC got a new IP from DHCP | Make a DHCP reservation, or update the OTA URL |
| The OTA request never appears in the server log | Firewall blocking 8003, or wrong IP in the OTA URL | Check the `ufw` rules and the URL |

> Using the device from **outside** the home network (for example from another city) is
> a different problem. Many ISPs use CGNAT, which makes port forwarding unreliable. A VPN
> like Tailscale or WireGuard is the usual answer. This guide only covers the local network.

---

## Scenario B: phone mobile hotspot

The phone acts as the router. The server PC and the board both connect to the hotspot,
and the phone gives both of them internet access through mobile data.

The catch: **the phone picks the subnet, and the IP changes between sessions.** Typical
ranges are `10.x.x.x` and `192.168.x.x` on Android, and `172.20.10.x` on iPhone. A
firmware URL compiled for home will not match, so set the OTA URL from the portal instead.

### Procedure

1. **Turn on the hotspot in 2.4 GHz.**
   - Android: Hotspot settings, then AP band, then **2.4 GHz**. The wording varies by brand.
   - iPhone: Personal Hotspot, then turn on **Maximize Compatibility**.
2. **Connect the server PC to the hotspot** and write down its IP, for example `10.199.165.189`.
3. **Make sure the firewall allows that subnet.** The three `ufw` rules above cover every case.
4. **Start the server.**
5. **Open the board's setup portal.** If the board cannot join any saved network, it
   starts its own access point named `Xiaozhi-XXXX`.
   - Connect the phone or the PC to that network.
   - Open **http://192.168.4.1** in a full browser such as Chrome. The automatic captive
     pop-up window can fail on the Advanced tab.
6. **Advanced tab:** set the Custom OTA URL to `http://10.199.165.189:8003/xiaozhi/ota/`
   (use your IP) and **save this tab first**.
7. **Wi-Fi tab:** choose the hotspot network, type its password and save. The board reboots
   and connects.

### Back home: undo the hotspot setting

The portal's Custom OTA URL **has priority over the firmware URL**. If you leave the
hotspot IP there, the board keeps looking for the server at that address on the home
network and fails.

When you return, open the portal again and **clear the Custom OTA URL**, or replace it
with the home URL.

### Common problems on hotspots

| Symptom | Cause | Fix |
|---------|-------|-----|
| The board does not see the hotspot | The hotspot is on 5 GHz | Switch to 2.4 GHz or Maximize Compatibility |
| Error on the Advanced tab of the portal | Captive pop-up window | Use Chrome at `http://192.168.4.1` |
| The board connects but never reaches the server | Wrong IP in the OTA URL, or the firewall blocks the hotspot subnet | Check the PC's current IP and the `ufw` rules |
| It worked last time, fails now | The phone gave the PC a new IP | Update the Custom OTA URL |
| Fails at home after using the hotspot | The Custom OTA URL still holds the hotspot IP | Clear it in the portal |

Mobile data is used by the server's calls to the cloud providers (audio and text), not
only by the board.

---

## Quick comparison

| | Home router (any ISP) | Phone hotspot |
|---|---|---|
| Who creates the network | The ISP's router | The phone |
| Server IP | Stable with a DHCP reservation | Changes between sessions |
| Where to set the OTA URL | Firmware (`CONFIG_OTA_URL`) | Portal Custom OTA URL |
| Internet for the AI providers | Home connection | Mobile data |
| Typical failures | Guest network, client isolation, DHCP changes | 5 GHz band, stale IP, leftover portal URL |

## Possible improvement: mDNS

Instead of an IP, the OTA URL could use the PC's mDNS name, for example
`http://xiaozhi-pc.local:8003/xiaozhi/ota/`. It would then work on any network without
changes. This needs `avahi` configured with a unique host name and UDP port 5353 open in
the firewall. It is not set up yet.
