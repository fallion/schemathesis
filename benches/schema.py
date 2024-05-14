import json
import pathlib

import pytest

import schemathesis
import hypothesis
from hypothesis import HealthCheck, Phase, Verbosity
from schemathesis.runner import from_schema

CURRENT_DIR = pathlib.Path(__file__).parent.absolute()
CATALOG_DIR = CURRENT_DIR / "data"


def read_from_catalog(path: str):
    with (CATALOG_DIR / path).open() as fd:
        return json.load(fd)


# Small size (~2k lines in YAML)
BBCI = read_from_catalog("bbci.json")
BBCI_SCHEMA = schemathesis.from_dict(BBCI)
BBCI_OPERATIONS = list(BBCI_SCHEMA.get_all_operations())
# Medium size (~8k lines in YAML)
VMWARE = read_from_catalog("vmware.json")
VMWARE_SCHEMA = schemathesis.from_dict(VMWARE)
VMWARE_OPERATIONS = list(VMWARE_SCHEMA.get_all_operations())
# Large size (~92k lines in YAML)
STRIPE = read_from_catalog("stripe.json")
STRIPE_SCHEMA = schemathesis.from_dict(STRIPE)


@pytest.mark.benchmark
@pytest.mark.parametrize("raw_schema", [BBCI, VMWARE], ids=("bbci", "vmware"))
def test_get_all_operations(raw_schema):
    schema = schemathesis.from_dict(raw_schema)

    for _ in schema.get_all_operations():
        pass


@pytest.mark.benchmark
@pytest.mark.parametrize("operations", [BBCI_OPERATIONS, VMWARE_OPERATIONS], ids=("bbci", "vmware"))
def test_as_json_schema(operations):
    for operation in operations:
        for parameter in operation.ok().iter_parameters():
            _ = parameter.as_json_schema(operation)


@pytest.mark.benchmark
def test_events():
    runner = from_schema(
        BBCI_SCHEMA,
        checks=(),
        count_operations=False,
        count_links=False,
        hypothesis_settings=hypothesis.settings(
            deadline=None,
            database=None,
            max_examples=1,
            derandomize=True,
            suppress_health_check=list(HealthCheck),
            phases=[Phase.explicit, Phase.generate],
            verbosity=Verbosity.quiet,
        ),
    )
    for _ in runner.execute():
        pass


@pytest.mark.benchmark
@pytest.mark.parametrize("raw_schema", [BBCI, VMWARE, STRIPE], ids=("bbci", "vmware", "stripe"))
def test_rewritten_components(raw_schema):
    schema = schemathesis.from_dict(raw_schema)

    _ = schema.rewritten_components


@pytest.mark.benchmark
@pytest.mark.parametrize("raw_schema", [BBCI, VMWARE, STRIPE], ids=("bbci", "vmware", "stripe"))
def test_links_count(raw_schema):
    schema = schemathesis.from_dict(raw_schema)

    _ = schema.links_count