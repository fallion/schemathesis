import pytest

import schemathesis
from schemathesis.checks import CheckContext
from schemathesis.core.failures import Failure
from schemathesis.core.transport import Response
from schemathesis.generation import GenerationMode
from schemathesis.generation.meta import (
    CaseMetadata,
    ComponentInfo,
    ComponentKind,
    GenerationInfo,
    PhaseInfo,
)
from schemathesis.openapi.checks import PositiveDataAcceptanceConfig
from schemathesis.specs.openapi.checks import (
    ResourcePath,
    _is_prefix_operation,
    has_only_additional_properties_in_non_body_parameters,
    negative_data_rejection,
    positive_data_acceptance,
    response_schema_conformance,
)


@pytest.mark.parametrize(
    ("lhs", "lhs_vars", "rhs", "rhs_vars", "expected"),
    [
        # Exact match, no variables
        ("/users/123", {}, "/users/123", {}, True),
        # Different paths, no variables
        ("/users/123", {}, "/users/456", {}, False),
        # Different variable names
        ("/users/{id}", {"id": "123"}, "/users/{user_id}", {"user_id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/users/{user_id}", {"user_id": "456"}, False),
        # Singular vs. plural
        ("/user/{id}", {"id": "123"}, "/users/{id}", {"id": "123"}, True),
        ("/user/{id}", {"id": "123"}, "/users/{id}", {"id": "456"}, False),
        ("/users/{id}", {"id": "123"}, "/user/{id}", {"id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/user/{id}", {"id": "456"}, False),
        # Trailing slashes
        ("/users/{id}/", {"id": "123"}, "/users/{id}", {"id": "123"}, True),
        ("/users/{id}/", {"id": "123"}, "/users/{id}", {"id": "456"}, False),
        ("/users/{id}", {"id": "123"}, "/users/{id}/", {"id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/users/{id}/", {"id": "456"}, False),
        ("/users/", {}, "/users", {}, True),
        ("/users", {}, "/users/", {}, True),
        # Empty paths
        ("", {}, "", {}, True),
        ("", {}, "/", {}, True),
        ("/", {}, "", {}, True),
        # Mismatched paths
        ("/users/{id}", {"id": "123"}, "/products/{id}", {"id": "456"}, False),
        ("/users/{id}", {"id": "123"}, "/users/{name}", {"name": "John"}, False),
        # LHS is a prefix of RHS
        ("/users/{id}", {"id": "123"}, "/users/{id}/details", {"id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/users/{id}/details", {"id": "456"}, False),
        # LHS is a prefix of RHS, with different number of variables
        ("/users/{id}", {"id": "123"}, "/users/{id}/{name}", {"id": "123", "name": "John"}, True),
        (
            "/users/{id}",
            {"id": "123"},
            "/users/{id}/{name}/{email}",
            {"id": "123", "name": "John", "email": "john@example.com"},
            True,
        ),
        # LHS is a prefix of RHS, with different variable values
        ("/users/{id}", {"id": "123"}, "/users/{id}/details", {"id": "123"}, True),
        # LHS is a prefix of RHS, with different variable types
        ("/users/{id}", {"id": "123"}, "/users/{id}/details", {"id": 123}, True),
        ("/users/{id}", {"id": 123}, "/users/{id}/details", {"id": "123"}, True),
        # LHS is a prefix of RHS, with extra path segments
        ("/users/{id}", {"id": "123"}, "/users/{id}/details/view", {"id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/users/{id}/details/view", {"id": "456"}, False),
        ("/users/{id}", {"id": "123"}, "/users/{id}/details/view/edit", {"id": "123"}, True),
        ("/users/{id}", {"id": "123"}, "/users/{id}/details/view/edit", {"id": "456"}, False),
        # Longer than a prefix
        ("/one/two/three/four/{id}", {"id": "123"}, "/users/{id}/details", {"id": "456"}, False),
    ],
)
def test_is_prefix_operation(lhs, lhs_vars, rhs, rhs_vars, expected):
    assert _is_prefix_operation(ResourcePath(lhs, lhs_vars), ResourcePath(rhs, rhs_vars)) == expected


def build_metadata(
    path_parameters=None, query=None, headers=None, cookies=None, body=None, generation_mode=GenerationMode.POSITIVE
):
    return CaseMetadata(
        generation=GenerationInfo(
            time=0.1,
            mode=generation_mode,
        ),
        components={
            kind: ComponentInfo(mode=value)
            for kind, value in [
                (ComponentKind.QUERY, query),
                (ComponentKind.PATH_PARAMETERS, path_parameters),
                (ComponentKind.HEADERS, headers),
                (ComponentKind.COOKIES, cookies),
                (ComponentKind.BODY, body),
            ]
            if value is not None
        },
        phase=PhaseInfo.generate(),
    )


@pytest.fixture
def sample_schema(ctx):
    return ctx.openapi.build_schema(
        {
            "/test": {
                "post": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "key",
                            "schema": {"type": "integer", "minimum": 5},
                        },
                        {
                            "in": "headers",
                            "name": "X-Key",
                            "schema": {"type": "integer", "minimum": 5},
                        },
                    ]
                }
            }
        }
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, False),
        (
            {"meta": build_metadata(body=GenerationMode.NEGATIVE)},
            False,
        ),
        (
            {
                "query": {"key": 1},
                "meta": build_metadata(query=GenerationMode.NEGATIVE),
            },
            False,
        ),
        (
            {
                "query": {"key": 1},
                "headers": {"X-Key": 42},
                "meta": build_metadata(query=GenerationMode.NEGATIVE),
            },
            False,
        ),
        (
            {
                "query": {"key": 5, "unknown": 3},
                "meta": build_metadata(query=GenerationMode.NEGATIVE),
            },
            True,
        ),
        (
            {
                "query": {"key": 5, "unknown": 3},
                "headers": {"X-Key": 42},
                "meta": build_metadata(query=GenerationMode.NEGATIVE),
            },
            True,
        ),
    ],
)
def test_has_only_additional_properties_in_non_body_parameters(sample_schema, kwargs, expected):
    schema = schemathesis.openapi.from_dict(sample_schema)
    operation = schema["/test"]["POST"]
    case = operation.Case(**kwargs)
    assert has_only_additional_properties_in_non_body_parameters(case) is expected


def test_negative_data_rejection_on_additional_properties(response_factory, sample_schema):
    # See GH-2312
    response = response_factory.requests()
    schema = schemathesis.openapi.from_dict(sample_schema)
    operation = schema["/test"]["POST"]
    case = operation.Case(
        meta=build_metadata(
            query=GenerationMode.NEGATIVE,
            generation_mode=GenerationMode.NEGATIVE,
        ),
        query={"key": 5, "unknown": 3},
    )
    assert (
        negative_data_rejection(
            CheckContext(
                override=None,
                auth=None,
                headers=None,
                config={},
                transport_kwargs=None,
            ),
            response,
            case,
        )
        is None
    )


def test_response_schema_conformance_with_unspecified_method(response_factory, sample_schema):
    response = response_factory.requests()
    response = Response.from_requests(response, True)
    sample_schema["paths"]["/test"]["post"]["responses"] = {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                        "required": ["id", "name"],
                    }
                }
            },
        }
    }
    schema = schemathesis.openapi.from_dict(sample_schema)
    operation = schema["/test"]["POST"]
    case = operation.Case(
        meta=CaseMetadata(
            generation=GenerationInfo(
                time=0.1,
                mode=GenerationMode.NEGATIVE,
            ),
            components={
                ComponentKind.QUERY: ComponentInfo(mode=GenerationMode.NEGATIVE),
            },
            phase=PhaseInfo.coverage(
                description="Unspecified HTTP method: PUT",
            ),
        ),
        query={"key": 5, "unknown": 3},
    )

    result = response_schema_conformance(
        CheckContext(
            override=None,
            auth=None,
            headers=None,
            config={},
            transport_kwargs=None,
        ),
        response,
        case,
    )
    assert result is True


@pytest.mark.parametrize(
    ("status_code", "allowed_statuses", "is_positive", "should_raise"),
    [
        (200, ["200", "400"], True, False),
        (400, ["200", "400"], True, False),
        (300, ["200", "400"], True, True),
        (200, ["2XX", "4XX"], True, False),
        (299, ["2XX", "4XX"], True, False),
        (400, ["2XX", "4XX"], True, False),
        (500, ["2XX", "4XX"], True, True),
        (200, ["200", "201", "400", "401"], True, False),
        (201, ["200", "201", "400", "401"], True, False),
        (400, ["200", "201", "400", "401"], True, False),
        (402, ["200", "201", "400", "401"], True, True),
        (200, ["2XX", "3XX", "4XX"], True, False),
        (300, ["2XX", "3XX", "4XX"], True, False),
        (400, ["2XX", "3XX", "4XX"], True, False),
        (500, ["2XX", "3XX", "4XX"], True, True),
        # Negative data, should not raise
        (200, ["200", "400"], False, False),
        (400, ["200", "400"], False, False),
    ],
)
def test_positive_data_acceptance(
    response_factory,
    sample_schema,
    status_code,
    allowed_statuses,
    is_positive,
    should_raise,
):
    schema = schemathesis.openapi.from_dict(sample_schema)
    operation = schema["/test"]["POST"]
    response = response_factory.requests(status_code=status_code)
    case = operation.Case(
        meta=build_metadata(
            query=GenerationMode.POSITIVE if is_positive else GenerationMode.NEGATIVE,
            generation_mode=GenerationMode.POSITIVE if is_positive else GenerationMode.NEGATIVE,
        ),
    )
    ctx = CheckContext(
        override=None,
        auth=None,
        headers=None,
        config={positive_data_acceptance: PositiveDataAcceptanceConfig(allowed_statuses=allowed_statuses)},
        transport_kwargs=None,
    )

    if should_raise:
        with pytest.raises(Failure) as exc_info:
            positive_data_acceptance(ctx, response, case)
        assert "Rejected positive data" in exc_info.value.title
    else:
        assert positive_data_acceptance(ctx, response, case) is None


@pytest.mark.parametrize(
    ["path", "header_name", "expected_status"],
    [
        ("/success", "X-API-Key-1", "200"),  # Does not fail
        ("/success", "X-API-Key-1", "406"),  # Fails because the response is HTTP 200
        ("/basic", "Authorization", "406"),  # Does not fail because Authorization has its own check
        ("/success", "Authorization", "200"),  # Fails because response is not 401
    ],
)
@pytest.mark.operations("success", "basic")
def test_missing_required_header(ctx, cli, openapi3_base_url, snapshot_cli, path, header_name, expected_status):
    schema_path = ctx.openapi.write_schema(
        {
            path: {
                "get": {
                    "parameters": [
                        {"name": header_name, "in": "header", "required": True, "schema": {"type": "string"}},
                        {"name": "X-API-Key-2", "in": "header", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }
    )
    assert (
        cli.run(
            str(schema_path),
            f"--url={openapi3_base_url}",
            "--hypothesis-phases=explicit",
            "--mode=negative",
            "--experimental=coverage-phase",
            f"--experimental-missing-required-header-allowed-statuses={expected_status}",
        )
        == snapshot_cli
    )


@pytest.mark.parametrize("path, method", [("/success", "get"), ("/basic", "post")])
@pytest.mark.operations("success")
def test_method_not_allowed(ctx, cli, openapi3_base_url, snapshot_cli, path, method):
    schema_path = ctx.openapi.write_schema(
        {
            path: {
                method: {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }
    )
    assert (
        cli.run(
            str(schema_path),
            f"--url={openapi3_base_url}",
            "--hypothesis-phases=explicit",
            "--mode=negative",
            "--experimental=coverage-phase",
        )
        == snapshot_cli
    )
