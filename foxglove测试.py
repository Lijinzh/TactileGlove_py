import websocket
import json


def send_to_foxglove(data):
    ws_url = "ws://127.0.0.1:8765"  # 确认端口和地址
    try:
        ws = websocket.create_connection(ws_url)
        # 这里的data应符合Foxglove的WebSocket协议格式
        data_dict = {
            "jsonrpc": "2.0",
            "method": "foxglove.websocket.v1",
            "params": {
                "data": data
            }
        }
        ws.send(json.dumps(data_dict))  # 发送数据
        ws.close()
    except Exception as e:
        print(f"发送到Foxglove Studio时发生错误: {str(e)}")

    # Example usage


sensor_data = {
    "sensors": [
        {
            "points": [
                {"x": 1, "y": 2, "z": 3},
                {"x": 4, "y": 5, "z": 6}
            ]
        }
    ]
}
send_to_foxglove(sensor_data)
