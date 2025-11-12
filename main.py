import asyncio
import os
from threading import Thread

import socketio
import uvicorn
from pymobiledevice3.cli.remote import TunnelProtocol
from pymobiledevice3.lockdown import LockdownServiceProvider
from pymobiledevice3.osu.os_utils import get_os_utils
from pymobiledevice3.services.dvt.instruments.location_simulation import (
    LocationSimulation,
)
from pymobiledevice3.services.dvt.instruments.process_control import (
    DvtSecureSocketProxyService,
)
from pymobiledevice3.tunneld.api import async_get_tunneld_devices
from pymobiledevice3.tunneld.server import TunneldRunner
from tenacity import retry, stop_after_attempt

service_provider: LockdownServiceProvider | None = None

# Routes to server
static_files = {
    "/": os.path.join(os.path.dirname(__file__), "index.html"),
    "/index.js": os.path.join(os.path.dirname(__file__), "index.js"),
    "/main.css": os.path.join(os.path.dirname(__file__), "main.css"),
}

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = socketio.ASGIApp(sio, static_files=static_files)

OSUTILS = get_os_utils()


@sio.event
async def location(sid, data):
    la, lo = list(map(lambda x: float(x), data.split(",")))
    print(la, lo)
    if service_provider is not None:
        with DvtSecureSocketProxyService(service_provider) as dvt:
            LocationSimulation(dvt).set(la, lo)


@retry(stop=stop_after_attempt(3))
async def init_location_simulator():
    """Initialize the location simulator with retry logic"""
    global service_provider

    try:
        rsds = await async_get_tunneld_devices(("127.0.0.1", 5555))
        print(rsds)
        if not rsds:
            raise RuntimeError("No devices found")

        device = rsds[0]

        await device.connect()

        service_provider = device

        print("Location simulator initialized successfully!")

    except IndexError:
        print("No device found, retrying...")
        raise
    except Exception as e:
        print(f"Error initializing location simulator: {e}")
        raise


def init_tunnel():
    TunneldRunner.create(
        "127.0.0.1",
        5555,
        protocol=TunnelProtocol.TCP,
        usb_monitor=True,
        wifi_monitor=True,
        usbmux_monitor=True,
        mobdev2_monitor=False,
    )


async def main():
    # Start tunnel in background thread
    tunnel_thread = Thread(target=init_tunnel, daemon=True)
    tunnel_thread.start()

    await asyncio.sleep(10)

    await init_location_simulator()

    config = uvicorn.Config(app, host="0.0.0.0", port=3000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        exit(1)
