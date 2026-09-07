import socket
import threading
import time

from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, Zeroconf


SERVICE_TYPE = "_chatid._tcp.local."


def get_lan_ip():
    """Return the local IPv4 address used to reach the current network."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        try:
            udp_socket.connect(("8.8.8.8", 80))
            return udp_socket.getsockname()[0]
        except OSError:
            return socket.gethostbyname(socket.gethostname())


def register_server(server_name, port):
    """Advertise a chat server on the local network and return its resources."""
    server_ip = get_lan_ip()
    service_info = ServiceInfo(
        SERVICE_TYPE,
        f"{server_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(server_ip)],
        port=port,
        properties={"name": server_name},
    )
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    zeroconf.register_service(service_info, allow_name_change=True)

    advertised_name = _short_name(service_info.name)
    return zeroconf, service_info, advertised_name, server_ip


def unregister_server(zeroconf, service_info):
    """Stop advertising a server and close Zeroconf cleanly."""
    zeroconf.unregister_service(service_info)
    zeroconf.close()


class _ServerListener:
    def __init__(self):
        self.servers = {}
        self.lock = threading.Lock()

    def add_service(self, zeroconf, service_type, name):
        self._save_service(zeroconf, service_type, name)

    def update_service(self, zeroconf, service_type, name):
        self._save_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type, name):
        with self.lock:
            self.servers.pop(name, None)

    def _save_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if info is None:
            return

        addresses = info.parsed_addresses(IPVersion.V4Only)
        if not addresses:
            return

        server = {
            "name": _short_name(name),
            "ip": addresses[0],
            "port": info.port,
        }
        with self.lock:
            self.servers[name] = server


def discover_servers(timeout=3.0):
    """Find chat servers advertised on the local network."""
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    listener = _ServerListener()
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener)

    try:
        time.sleep(timeout)
        with listener.lock:
            return sorted(listener.servers.values(), key=lambda item: item["name"])
    finally:
        browser.cancel()
        zeroconf.close()


def _short_name(full_name):
    return full_name.removesuffix(SERVICE_TYPE).rstrip(".")
