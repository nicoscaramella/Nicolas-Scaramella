import asyncio

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_lista_tools_mcp():
    params = StdioServerParameters(command="python", args=["-m", "sistema.mcp_server"])

    async def listar():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.list_tools()

    resultado = await asyncio.wait_for(listar(), timeout=40)
    nombres = {t.name for t in resultado.tools}
    assert {
        "equipos", "historial_sensores", "buscar_manuales", "traducir_codigo_falla"
    } <= nombres
