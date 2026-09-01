# sprint_execution/sse.py
from django.http import StreamingHttpResponse
import time

class SSEEventStream:
    def __init__(self):
        self.latest_event = None

    def publish(self, data):
        self.latest_event = data

sse_event_stream = SSEEventStream()

def sse_event_generator():
    while True:
        if sse_event_stream.latest_event:
            yield f"data: {sse_event_stream.latest_event}\n\n"
            sse_event_stream.latest_event = None
        time.sleep(1)

def task_event_stream(request):
    response = StreamingHttpResponse(sse_event_generator(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    return response

def send_sse_message(event, data):
    import json
    payload = {
        "event": event,
        "data": data
    }
    sse_event_stream.publish(json.dumps(payload))
