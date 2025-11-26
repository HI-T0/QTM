import json
import time

class Message:
    """Network message protocol"""
    REQUEST_CHAIN = "REQUEST_CHAIN"
    SEND_CHAIN = "SEND_CHAIN"
    NEW_BLOCK = "NEW_BLOCK"
    NEW_TRANSACTION = "NEW_TRANSACTION"
    REQUEST_PEERS = "REQUEST_PEERS"
    SEND_PEERS = "SEND_PEERS"
    PING = "PING"
    PONG = "PONG"
    
    def __init__(self, msg_type: str, data: any):
        self.type = msg_type
        self.data = data
        self.timestamp = time.time()
    
    def to_json(self) -> str:
        """Serialize message to JSON"""
        return json.dumps({
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp
        })
    
    @staticmethod
    def from_json(json_str: str):
        """Deserialize message from JSON"""
        data = json.loads(json_str)
        msg = Message(data['type'], data['data'])
        # preserve timestamp if provided
        msg.timestamp = data.get('timestamp', time.time())
        return msg