import redis

from ..backend import DEFAULT_TIMEOUT, ResultBackend, ResultMissing, ResultTimeout


class RedisBackend(ResultBackend):
    """A result backend for Redis_.  This is the recommended result
    backend as waiting for a result is resource efficient.

    Parameters:
      namespace(str): A string with which to prefix result keys.
      encoder(Encoder): The encoder to use when storing and retrieving
        result data.  Defaults to :class:`.JSONEncoder`.
      client(StrictRedis): An optional client.  If this is passed,
        then all other parameters are ignored.
      \**parameters(dict): Connection parameters are passed directly
        to :class:`redis.StrictRedis`.

    .. _redis: https://redis.io
    """

    def __init__(self, *, namespace="dramatiq-results", encoder=None, client=None, **parameters):
        super().__init__(namespace=namespace, encoder=encoder)
        self.client = client or redis.StrictRedis(**parameters)

    def get_result(self, message, *, block=False, timeout=None):
        """Get a result from the backend.

        Warning:
          Sub-second timeouts are not respected by this backend.

        Parameters:
          message(Message)
          block(bool): Whether or not to block until a result is set.
          timeout(int): The maximum amount of time, in ms, to wait for
            a result when block is True.  Defaults to 10 seconds.

        Raises:
          ResultMissing: When block is False and the result isn't set.
          ResultTimeout: When waiting for a result times out.

        Returns:
          object: The result.
        """
        timeout = timeout or DEFAULT_TIMEOUT
        message_key = self.build_message_key(message)
        if block:
            timeout = int(timeout / 1000)
            if timeout == 0:
                data = self.client.rpoplpush(message_key, message_key)
            else:
                data = self.client.brpoplpush(message_key, message_key, timeout)

            if data is None:
                raise ResultTimeout(message)

        else:
            data = self.client.lindex(message_key, 0)
            if data is None:
                raise ResultMissing(message)

        return self.encoder.decode(data)

    def _store(self, message_key, result, ttl):
        with self.client.pipeline() as pipe:
            pipe.delete(message_key)
            pipe.lpush(message_key, self.encoder.encode(result))
            pipe.pexpire(message_key, ttl)
            pipe.execute()
