import yaml
from typing import Dict


def load_config(config_path: str) -> Dict:
    """Load the YAML test-framework configuration file.

    Parameters
    ----------
    config_path:
        Path to a YAML file (e.g. ``config/config.yaml``) containing the
        ``testing``, ``ammeters``, ``analysis``, and ``result_management``
        sections consumed by :class:`src.testing.test_framework.AmmeterTestFramework`.

    Returns
    -------
    Dict
        Parsed configuration as nested dictionaries/lists.
    """
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

