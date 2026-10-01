# Message bus middleware

Needs the `messenger` extra: `uv add "xtr-orm[messenger]"`. With both bundles active, importing
`xtr_orm.messenger` is done for you and each middleware is registered under its name for a bus
configuration to list.

| Name | Class | Does | Arguments |
|---|---|---|---|
| `orm_transaction` | `TransactionMiddleware` | Runs every handler of a message in one transaction, committed once they all succeeded and rolled back otherwise. A failure drops the other handlers' handled stamps, so a retry runs them all again | `connection_name`, the default connection when left out |
| `orm_close_connection` | `CloseConnectionMiddleware` | Closes the connections once a worker handled a message it consumed, so an idle worker holds none — once the last, when it handles several at once | `connection_names`, every connection in use when left out |
| `orm_open_transaction_logger` | `OpenTransactionLoggerMiddleware` | Logs an error when a handler began a transaction (`begin()`, `begin_nested()`) and left it open in a message that was handled | `connection_names`, as above |

"In use" means a connection whose engine has been built; opening one to find out would read its
configuration, so an untouched connection is left alone.

## Order

```python
# <app>/config/messenger.py
MessageBusConfig(
    middleware=[
        "orm_close_connection",
        "orm_transaction",
        {"orm_transaction": {"connection_name": "reports"}},
        "orm_open_transaction_logger",
    ],
)
```

- `orm_close_connection` outermost, so it closes after the transaction ended.
- `orm_open_transaction_logger` inside `orm_transaction`, so it looks before the commit closes
  everything.
- A second `orm_transaction` with another `connection_name` puts that connection in a transaction
  too.

## Handlers

```python
# app/billing/handlers.py
@as_message_handler(IssueInvoice)
async def issue(message: IssueInvoice, session: Injected[AsyncSession]) -> None:
    session.add(Invoice(order_id=message.order_id))  # no commit


@as_message_handler(IssueInvoice)
class NotifyAccounting:
    # A scoped repository on the same session: one transaction for both handlers.
    async def __call__(
        self, message: IssueInvoice, invoices: Injected[InvoiceRepository]
    ) -> None: ...
```

- **One session per message.** Every handler of the message, and every scoped service built on the
  session, gets the same one, released once the message is done with.
- **A nested dispatch joins the unit of work** and its transaction, in a savepoint of its own: when
  it fails only its handlers' work is rolled back, and the handler that dispatched it decides
  whether the rest goes on.
- **Handlers do not commit.** One that does ends the transaction early; one using
  `async with session.begin()` is refused, the transaction being open already.
- **Follow-ups wait for the commit only when stamped.** A message dispatched to a transport is
  sent at once, before the commit and whether or not it comes:

  ```python
  await bus.dispatch(SendReceipt(order.id), DispatchAfterCurrentBusStamp())
  ```

  With that stamp it goes out only once the message being handled was committed, and never after a
  rollback.
- **Only messages a worker consumed** — one carrying a `ReceivedStamp` on arrival — close
  connections afterwards. A message handled during its dispatch, `sync://` included, closes
  nothing. A worker handling several at once closes once the last is done.
- **A dropped connection** is found by the engine option `pool_pre_ping` as a connection is taken
  from the pool (`?pool_pre_ping=true` on a worker's URL), so there is no middleware for it.

## Without a container

Build the middleware yourself and put the instances in the bus configuration. They need a
`ConnectionRegistry` whose connections were registered with a `session` callable — what returns the
session the handlers use — or `registry.session()` raises `SessionUnavailableError`.

```python
from xtr_orm.messenger import (
    CloseConnectionMiddleware,
    OpenTransactionLoggerMiddleware,
    TransactionMiddleware,
)

middleware = [
    CloseConnectionMiddleware(registry),
    TransactionMiddleware(registry),
    OpenTransactionLoggerMiddleware(registry),
]
```

`connection_names` takes one name or a sequence of them.
