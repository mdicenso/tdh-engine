import reflex as rx

config = rx.Config(
    app_name="tdh_reflex_poc",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)