import os, json
from aiokafka import AIOKafkaProducer


class Bus:
    def __init__(self, bootstrap: str | None = None):
        self.bootstrap = bootstrap or os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap)


    async def start(self):
        await self.producer.start()


    async def stop(self):
        await self.producer.stop()


    async def emit(self, topic: str, key: str, payload: dict):
        await self.producer.send_and_wait(topic, json.dumps(payload, ensure_ascii=False).encode(), key=key.encode())