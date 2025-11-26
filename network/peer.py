from dataclasses import dataclass

@dataclass
class Peer:
    """Represents a peer node"""
    host: str
    port: int
    
    def __hash__(self):
        return hash(f"{self.host}:{self.port}")
    
    def __eq__(self, other):
        return self.host == other.host and self.port == other.port
    
    def __str__(self):
        return f"{self.host}:{self.port}"
