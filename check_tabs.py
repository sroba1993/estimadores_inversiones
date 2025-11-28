import dash_bootstrap_components as dbc
from dash import dcc, html

tabs = dbc.Tabs(
    [
        dbc.Tab(
            dcc.Loading(
                html.Pre(
                    id="info-text"
                ),
                type="default",
            ),
            label="Resumen fundamental",
            tab_id="tab-resumen",
        ),
        dbc.Tab(
            dcc.Loading(
                html.Pre(
                    id="balance-text"
                ),
                type="default",
            ),
            label="Balance Sheet",
            tab_id="tab-balance",
        ),
        dbc.Tab(
            dcc.Loading(
                html.Pre(
                    id="income-text"
                ),
                type="default",
            ),
            label="Income Statement",
            tab_id="tab-income",
        ),
    ],
    active_tab="tab-resumen",
    className="mt-2",
    pills=True,
)

print("Tabs created successfully")

