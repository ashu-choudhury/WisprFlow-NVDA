from collections.abc import Iterable
from typing import Protocol

from wisprflow.models import RuntimeRoute


class Transport(Protocol):
    def stream(
        self,
        requests: Iterable[bytes],
        *,
        route: RuntimeRoute,
        access_token: str,
        timeout: float,
    ) -> Iterable[bytes]: ...


class GrpcTransport:
    def stream(
        self,
        requests: Iterable[bytes],
        *,
        route: RuntimeRoute,
        access_token: str,
        timeout: float,
    ) -> Iterable[bytes]:
        import grpc

        options = [
            ("grpc.max_send_message_length", 64 * 1024 * 1024),
            ("grpc.max_receive_message_length", 64 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 15000),
            ("grpc.keepalive_timeout_ms", 5000),
        ]
        channel = grpc.secure_channel(
            f"{route.host}:{route.port}",
            grpc.ssl_channel_credentials(),
            options=options,
        )
        method = channel.stream_stream(
            route.method,
            request_serializer=lambda value: value,
            response_deserializer=lambda value: value,
        )
        try:
            yield from method(
                requests,
                metadata=route.metadata(access_token),
                timeout=timeout,
            )
        finally:
            channel.close()
