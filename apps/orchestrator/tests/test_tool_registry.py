from app.tools.registry import TOOL_EXECUTORS, TOOL_SCHEMAS, is_destructive


def test_schemas_match_registered_executors() -> None:
    schema_names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert schema_names == set(TOOL_EXECUTORS)


def test_only_actualizar_nota_is_destructive() -> None:
    assert is_destructive("actualizar_nota") is True
    assert is_destructive("crear_nota") is False
    assert is_destructive("buscar_nota") is False
    assert is_destructive("listar_tareas") is False
