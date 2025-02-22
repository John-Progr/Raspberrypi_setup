from typing import Set, List, Dict, Any, Optional, Collection
from dataclasses import dataclass
import socket
import json
from collections import defaultdict

@dataclass
class Interface:
    name: str = ""

@dataclass
class Gateway:
    ipAddress: str = ""
    status: str = ""
    etx: float = 0.0
    hopcount: int = 0
    uplink: int = 0
    downlink: int = 0
    ipv4: bool = False
    ipv6: bool = False
    prefix: str = ""

@dataclass
class HNA:
    destination: str = ""
    gateway: str = ""

@dataclass
class Link:
    localIP: str = ""
    remoteIP: str = ""
    hysteresis: float = 0.0
    lq: float = 0.0
    nlq: float = 0.0
    cost: float = 0.0

@dataclass
class MID:
    ipAddress: str = ""
    aliases: List[str] = None

@dataclass
class Neighbor:
    ipv4Address: str = ""
    symmetric: bool = False
    multiPointRelay: bool = False  # Changed from 'mpr'
    multiPointRelaySelector: bool = False  # Changed from 'mprs'
    willingness: int = 0
    twoHopNeighbors: List[str] = None
    twoHopNeighborCount: int = 0  # Added new field

@dataclass
class Node:
    destinationIP: str = ""
    lastHopIP: str = ""
    lq: float = 0.0
    nlq: float = 0.0
    cost: float = 0.0

@dataclass
class Route:
    destination: str = ""
    gateway: str = ""
    metric: int = 0
    etx: float = 0.0
    interface: str = ""

@dataclass
class Plugin:
    plugin: str = ""
    config: Dict[str, Any] = None

@dataclass
class Config:
    pass

@dataclass
class OlsrDataDump:
    config: Config = None
    gateways: List[Gateway] = None
    hna: List[HNA] = None
    interfaces: List[Interface] = None
    links: List[Link] = None
    mid: List[MID] = None
    neighbors: List[Neighbor] = None
    topology: List[Node] = None
    plugins: List[Plugin] = None
    routes: List[Route] = None
    raw: str = ""

    def __post_init__(self):
        # Initialize empty lists/objects if None
        self.config = self.config or Config()
        self.gateways = self.gateways or []
        self.hna = self.hna or []
        self.interfaces = self.interfaces or []
        self.links = self.links or []
        self.mid = self.mid or []
        self.neighbors = self.neighbors or []
        self.topology = self.topology or []
        self.plugins = self.plugins or []
        self.routes = self.routes or []

class JsonInfo:
    def __init__(self, host: str = "127.0.0.1", port: int = 9090):
        self.host = host
        self.port = port
        self.last_command = ""
        
        self.supported_commands = {
            # combined reports
            "all",          # all of the JSON info
            "runtime",      # all of the runtime status reports
            "startup",      # all of the startup config reports
            
            # individual runtime reports
            "gateways",     # gateways
            "hna",         # Host and Network Association
            "interfaces",   # network interfaces
            "links",       # links
            "mid",         # MID
            "neighbors",    # neighbors
            "routes",      # routes
            "topology",    # mesh network topology
            "runtime",     # all the runtime info in a single report
            
            # the rest don't change at runtime
            "config",      # current running config info
            "plugins",     # loaded plugins and their config
            
            # only non-JSON output
            "olsrd.conf"   # current config in olsrd.conf format
        }

    def is_command_string_valid(self, cmd_string: str) -> bool:
        """Validate if the command string is supported."""
        is_valid = True
        if cmd_string != self.last_command:
            self.last_command = cmd_string
            for s in [x for x in cmd_string.split("/") if x]:
                if s not in self.supported_commands:
                    print(f"Unsupported command: {s}")
                    is_valid = False
        return is_valid

    def request(self, req: str) -> List[str]:
        """Request a reply from the jsoninfo plugin via a network socket."""
        ret_list = []
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.host, self.port))
                sock.sendall(f"{req}\n".encode())
                
                # Receive data
                data = b""
                while True:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    data += chunk
                
                # Process received data
                ret_list = [line for line in data.decode().split("\n") if line]
                
        except socket.gaierror:
            print(f"Unknown host: {self.host}")
        except ConnectionRefusedError:
            print(f"Couldn't get I/O for socket to {self.host}:{self.port}")
        except Exception as e:
            print(f"Error during request: {str(e)}")
            
        return ret_list

    def command(self, cmd_string: str) -> str:
        """Send a command and get raw response."""
        if not self.is_command_string_valid(cmd_string):
            return ""
            
        try:
            data = self.request(cmd_string)
            return "\n".join(data) + "\n"
        except Exception as e:
            print(f"Failed to read data from {self.host}:{self.port}")
            print(f"Error: {str(e)}")
            return ""

    def parse_command(self, cmd: str) -> OlsrDataDump:
        """Parse command response into Python objects."""
        ret = OlsrDataDump()
        try:
            dump = self.command(cmd)
            if dump:
                # Parse JSON into dictionary
                data = json.loads(dump)
                
                # Map the data to our classes
                if 'config' in data:
                    ret.config = Config(**data['config'])
                if 'gateways' in data:
                    ret.gateways = [Gateway(**g) for g in data['gateways']]
                if 'hna' in data:
                    ret.hna = [HNA(**h) for h in data['hna']]
                if 'interfaces' in data:
                    ret.interfaces = [Interface(**i) for i in data['interfaces']]
                if 'links' in data:
                    ret.links = [Link(**l) for l in data['links']]
                if 'mid' in data:
                    ret.mid = [MID(**m) for m in data['mid']]
                if 'neighbors' in data:
                    ret.neighbors = [Neighbor(**n) for n in data['neighbors']]
                if 'topology' in data:
                    ret.topology = [Node(**t) for t in data['topology']]
                if 'plugins' in data:
                    ret.plugins = [Plugin(**p) for p in data['plugins']]
                if 'routes' in data:
                    ret.routes = [Route(**r) for r in data['routes']]
                
                ret.raw = dump
                
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")
        except Exception as e:
            print(f"Error during parsing: {str(e)}")
            
        return ret

    # Convenience methods for specific commands
    def all(self) -> OlsrDataDump:
        return self.parse_command("/all")

    def runtime(self) -> OlsrDataDump:
        return self.parse_command("/runtime")

    def startup(self) -> OlsrDataDump:
        return self.parse_command("/startup")

    def neighbors(self) -> List[Neighbor]:
        return self.parse_command("/neighbors").neighbors

    def links(self) -> List[Link]:
        return self.parse_command("/links").links

    def routes(self) -> List[Route]:
        return self.parse_command("/routes").routes

    def hna(self) -> List[HNA]:
        return self.parse_command("/hna").hna

    def mid(self) -> List[MID]:
        return self.parse_command("/mid").mid

    def topology(self) -> List[Node]:
        return self.parse_command("/topology").topology

    def interfaces(self) -> List[Interface]:
        return self.parse_command("/interfaces").interfaces

    def gateways(self) -> List[Gateway]:
        return self.parse_command("/gateways").gateways

    def config(self) -> Config:
        return self.parse_command("/config").config

    def plugins(self) -> List[Plugin]:
        return self.parse_command("/plugins").plugins

    def olsrdconf(self) -> str:
        return self.command("/olsrd.conf")

# Example usage
if __name__ == "__main__":
    jsoninfo = JsonInfo()
    dump = jsoninfo.all()
    
    print("Gateways:")
    for g in dump.gateways:
        print(f"\t{g.ipAddress}")
    
    print("HNA:")
    for h in dump.hna:
        print(f"\t{h.destination}")
    
    print("Interfaces:")
    for i in dump.interfaces:
        print(f"\t{i.name}")
    
    print("Links:")
    for l in dump.links:
        print(f"\t{l.localIP} <--> {l.remoteIP}")
    
    print("MID:")
    for m in dump.mid:
        print(f"\t{m.ipAddress}")
    
    print("Neighbors:")
    for n in dump.neighbors:
        print(f"\t{n.ipv4Address}")
    
    print("Plugins:")
    for p in dump.plugins:
        print(f"\t{p.plugin}")
    
    print("Routes:")
    for r in dump.routes:
        print(f"\t{r.destination}")
    
    print("Topology:")
    for node in dump.topology:
        print(f"\t{node.destinationIP}")
