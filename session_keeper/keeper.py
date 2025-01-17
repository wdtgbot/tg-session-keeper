from typing import List, Optional, Union

import telethon
from telethon.tl import types as tl_types

from session_keeper import session as _session
from session_keeper import storage as _storage
from session_keeper.version import __version__ as keeper_version

INDEX_ERROR_NON_EXISTENT_SESSION = IndexError("There is no session with this number.")
INDEX_ERROR_MISSING_MESSAGES = IndexError("Messages from Telegram are missing.")


class Keeper:
    _clients: List[telethon.TelegramClient]
    _client_for_login: Optional[telethon.TelegramClient]

    def __init__(self, storage: _storage.AbstractStorage, test_mode: bool = False):
        self._storage = storage
        self._test_mode = test_mode
        self._clients = []
        self._started = False
        self._client_for_login = None

    @property
    def started(self) -> bool:
        return self._started

    @property
    def storage(self) -> _storage.AbstractStorage:
        return self._storage

    @property
    def test_mode(self) -> bool:
        return self._test_mode

    async def add(self, phone: str) -> None:
        self._client_for_login = client = telethon.TelegramClient(  # type: ignore
            _session.Session(),
            self._storage.api_id,
            self._storage.api_hash,
            app_version=f"Session Keeper {keeper_version}",
        )
        if self.test_mode:
            client.session.set_dc(2, "149.154.167.40", 443)
        await client.connect()
        await client.get_me()
        await client.send_code_request(phone)

    async def login_add_code_and_password(
        self, code: Union[str, int], password: Optional[str] = None
    ) -> None:
        await self._client_for_login.sign_in(  # type: ignore
            code=code,
            password=password,
        )
        await self._storage.add_session(self._client_for_login.session)  # type: ignore
        self._clients.append(self._client_for_login)
        self._client_for_login = None

    async def remove(self, number: int) -> None:
        try:
            client = self._clients.pop(number)
        except IndexError as error:
            raise INDEX_ERROR_NON_EXISTENT_SESSION from error
        await self._storage.remove_session(number)
        await client.log_out()

    async def list(self) -> List[_session.Session]:
        return self._storage.sessions

    async def get(self, number: int) -> tl_types.Message:
        try:
            client = self._clients[number]
        except IndexError as error:
            raise INDEX_ERROR_NON_EXISTENT_SESSION from error
        try:
            return (await client.get_messages(777000))[0]
        except IndexError as error:
            raise INDEX_ERROR_MISSING_MESSAGES from error

    async def setup_storage(self, api_id: int, api_hash: str) -> None:
        await self._storage.setup(api_id, api_hash)

    async def start(self) -> None:
        storage = self._storage

        await storage.start()

        for session in storage.sessions:
            client = telethon.TelegramClient(session, storage.api_id, storage.api_hash)
            await client.connect()
            await client.get_me()
            self._clients.append(client)

        self._started = True

    async def stop(self) -> None:
        if self._client_for_login:
            await self._client_for_login.disconnect()
        for client in self._clients:
            await client.disconnect()
        await self._storage.stop()
        self._started = False

    @classmethod
    def init_with_ejs(
        cls, password: Union[bytes, str], filename: str, test_mode: bool = False
    ) -> "Keeper":
        return cls(
            _storage.EncryptedJsonStorage(password, filename),
            test_mode=test_mode,
        )
