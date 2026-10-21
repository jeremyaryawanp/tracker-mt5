from fasthtml.common import A, Body, Div, Footer, Header, Main, Nav, Span, Title

NAV_ITEMS = [
    ("/", "Dashboard"),
    ("/calendar", "Calendar"),
    ("/analytics", "Pairs & Strategy"),
    ("/trades", "Journal"),
    ("/review", "Weekly Review"),
    ("/accounts", "Accounts & Sync"),
]


def page(title: str, *content, active: str = "/", user: str | None = None):
    links = [
        A(
            label,
            href=href,
            cls="px-3 py-2 rounded-md text-sm "
            + ("bg-slate-800 text-white" if href == active else "text-slate-400 hover:text-white"),
        )
        for href, label in NAV_ITEMS
    ]
    right = [Span(user, cls="text-slate-500 text-sm")] if user else []
    if user:
        right.append(A("Logout", href="/logout", cls="text-slate-400 hover:text-white text-sm"))
    return (
        Title(f"{title} · TradeJournal AI"),
        Body(
            Header(
                Nav(
                    A("TradeJournal AI", href="/", cls="font-semibold text-white mr-6"),
                    Div(*links, cls="flex flex-wrap gap-1"),
                    Div(*right, cls="ml-auto flex items-center gap-3"),
                    cls="max-w-7xl mx-auto flex items-center px-4 py-3",
                ),
                cls="border-b border-slate-800 bg-slate-950/80 sticky top-0 z-10 backdrop-blur",
            ),
            Main(*content, cls="max-w-7xl mx-auto px-4 py-6 space-y-6"),
            Footer(
                "Analytical tool only — never places, modifies, or closes orders.",
                cls="max-w-7xl mx-auto px-4 py-6 text-xs text-slate-600",
            ),
            cls="bg-slate-950 text-slate-200 min-h-screen",
        ),
    )


def card(*content, cls: str = ""):
    return Div(*content, cls=f"rounded-xl border border-slate-800 bg-slate-900/60 p-4 {cls}")


def empty_state(message: str, hint: str | None = None):
    return card(
        Div(message, cls="text-slate-300"),
        Div(hint, cls="text-slate-500 text-sm mt-1") if hint else "",
        cls="text-center py-10",
    )
