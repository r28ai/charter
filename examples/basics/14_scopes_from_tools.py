"""Ask your users for the OAuth scopes your tools need, computed from the tools themselves."""

from charter.auth import scopes_for
from charter.packs import gcalendar, gmail

reader = [gmail.messages_list, gmail.messages_get, gcalendar.events_list]
cleaner = [*reader, gmail.threads_delete]

for name, tools in (("reader", reader), ("cleaner", cleaner)):
    scopes = (s.removeprefix("https://www.googleapis.com/auth/") for s in scopes_for(tools))
    print(f"a {name:7} asks for  {', '.join(scopes)}")
# a reader  asks for  gmail.modify, calendar.events
# a cleaner asks for  gmail.modify, calendar.events, https://mail.google.com/  <- the whole mailbox
