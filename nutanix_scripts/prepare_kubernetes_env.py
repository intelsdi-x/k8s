# Copyright (c) 2017 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Run this script to prepare environment for kubernetes"""

import re
import os
import time

import yaml
import jinja2

from nutanix_scripts.api import Nutanix
from nutanix_scripts.exceptions import ConfigurationError, MissingKeys
from nutanix_scripts.logger import logger

# URL for CentOS Image used for VM creation process.
OS_IMAGE_URL = 'http://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud-1702.qcow2c'

# Name, VCPUs, RAM(GB), Disk Size(GB) of Virtual Machine used as base vm.
# Other machines will be cloned from it.
BASE_VM_CPU = 2
BASE_VM_RAM = 4
BASE_VM_DISK = 10

# Configuration and "templating" for ansible inventory.
INVENTORY_FILE = 'inventory'

# Names of config files for clusters and virtual environments for installer.
K8S_CONFIG = 'configs/k8s_cluster.yml'
NUTANIX_CONFIG = 'configs/nutanix_cluster.yml'

NUTANIX_CLUSTER_ENV = 'NUTANIX_CLUSTER'
K8S_CLUSTER_ENV = 'K8S_CLUSTER'
BASE_VM_ENV = 'BASE_VM_NAME'
SSH_DIR_ENV = 'SSH_DIR'

SUPPORTED_NUMBER_OF_MASTERS = (1, 3, 5)
DEFAULT_NUMBER_OF_NODES = 3
DEFAULT_NUMBER_OF_RAM = 4
DEFAULT_NUMBER_OF_VCPU = 2

DOMAIN_NAME = re.compile(
    r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$'
)

CLOUD_CONFIG_HEADER = "\n".join((
    "#cloud-config",
    "users:"
))
CLOUD_CONFIG_USER_PART = "\n".join((
    "  - name: {username}",
    "    shell: /bin/bash",
    "    sudo: ['ALL=(ALL) NOPASSWD:ALL']",
    "    lock_passwd: true",
    "    ssh-authorized-keys:",
    "      - {ssh_key}"
))
SSH_KEY_FILE_PATTERN = re.compile(r'(?P<username>[a-z_][a-z0-9_-]*[$]?)\.pub')


def generate_cloud_config(ssh_keys_directory):
    """Generate cloud config based on ssh keys.
     Ssh keys should have username.pub format.

    :param str ssh_keys_directory: directory with ssh_keys
    :return: cloud config
    :rtype: string
    :raises IOError: when directory/file doesn't exist, or path is incorrect.
    :raises MissinKey: when there are no files matching pattern in ssh keys directory

    """
    cloud_config_parts = []
    for file_name in os.listdir(ssh_keys_directory):
        pattern_match = SSH_KEY_FILE_PATTERN.match(file_name)
        if not pattern_match:
            continue
        with open(os.path.join(ssh_keys_directory, file_name)) as ssh_key:
            cloud_config_parts.append(
                CLOUD_CONFIG_USER_PART.format(
                    username=pattern_match.group('username'),
                    ssh_key=ssh_key.read().strip()
                )
            )

    if not cloud_config_parts:
        raise MissingKeys(MissingKeys.MESSAGE.format(SSH_KEY_FILE_PATTERN.pattern))
    else:
        cloud_config_parts.insert(0, CLOUD_CONFIG_HEADER)

    cloud_config = '\n'.join(cloud_config_parts)
    logger.info('Prepared cloud config for vms.\n%s', cloud_config)
    return cloud_config


def get_kubernetes_config(config_path):
    """Open kubernetes cluster configuration file and load it's content.
    Return tupple with common, master and worker configs.

    :param str config_path: path to config file, default **k8s_cluster.yml**
    :return: Tupple with common, master and worker config.
    :rtype: tuple
    :raises IOError: when file doesn't exist, or path is incorrect.
    :raises ParseError: when file is not valid yml file.
    :raises ConfigurationError: when configuration file is incorrect.

    """
    logger.info('Reading cluster configuration from %s', config_path)
    with open(config_path) as conf_file:
        data = yaml.safe_load(conf_file)

    try:
        common_config = data['common']
    except KeyError:
        raise ConfigurationError(ConfigurationError.MISSING_SECTION.format('common'))

    try:
        _tmp_config = data.get('master', {})
        master_config = {
            'role': 'master',
            'number_of_nodes': int(
                _tmp_config.get('number_of_nodes', DEFAULT_NUMBER_OF_NODES)
            ),
            'number_of_vcpu': int(
                _tmp_config.get('number_of_vcpu', DEFAULT_NUMBER_OF_VCPU)
            ),
            'ram_size': int(
                _tmp_config.get('ram_size', DEFAULT_NUMBER_OF_RAM)
            )
        }
        if master_config['number_of_nodes'] not in SUPPORTED_NUMBER_OF_MASTERS:
            raise ConfigurationError(
                ConfigurationError.INVALID_NUMBER_OF_MASTERS.format(
                    SUPPORTED_NUMBER_OF_MASTERS
                )
            )
        _tmp_config = data.get('worker', {})
        worker_config = {
            'role': 'worker',
            'number_of_nodes': int(
                _tmp_config.get('number_of_nodes', DEFAULT_NUMBER_OF_NODES)
            ),
            'number_of_vcpu': int(
                _tmp_config.get('number_of_vcpu', DEFAULT_NUMBER_OF_VCPU)
            ),
            'ram_size': int(
                _tmp_config.get('ram_size', DEFAULT_NUMBER_OF_RAM)
            )
        }

    except ValueError as error:
        raise ConfigurationError(ConfigurationError.INVALID_TYPE.format(error.message))
    else:
        return common_config, master_config, worker_config


def get_persistent_volumes_config(config_path):
    """Open kubernetes cluster configuration file and load peristent volumes content.
    Return dictionary with information needed to generate storage classes files.

    :param str config_path: path to config file, default **k8s_cluster.yml**
    :return: Dictionary with information needed to generate storage classes.
    :rtype: dict
    :raises IOError: when file doesn't exist, or path is incorrect.
    :raises ParseError: when file is not valid yml file.
    :raises ConfigurationError: when configuration file is incorrect.

    """
    logger.info('Reading cluster configuration from %s', config_path)
    with open(config_path) as conf_file:
        data = yaml.safe_load(conf_file)

    try:
        persistent_volumes_config = data['persistent_storage']
    except KeyError:
        raise ConfigurationError(ConfigurationError.MISSING_SECTION.format('persistent_storage'))

    try:
        config = {
            'silver': {
                'enabled': persistent_volumes_config['silver']['enabled'],
                'filesystem': persistent_volumes_config['silver']['filesystem'],
                'storage_container': persistent_volumes_config['silver']['storage_container_name'],
                'iqn': persistent_volumes_config['iqn'],
                'data_service_endpoint': persistent_volumes_config['data_service_endpoint']
            },
            'gold': {
                'enabled': persistent_volumes_config['gold']['enabled'],
                'filesystem': persistent_volumes_config['gold']['filesystem'],
                'storage_container': persistent_volumes_config['gold']['storage_container_name'],
                'iqn': persistent_volumes_config['iqn'],
                'data_service_endpoint': persistent_volumes_config['data_service_endpoint']
            }
        }
    except KeyError as error:
        raise ConfigurationError(ConfigurationError.MISSING_FIELD.format(error))
    else:
        return config


def prepare_env():
    """This function implements main logic of preparation Virtual machines
    for Kubernetes installation:

    * Read configs from files.
    * Validates Nutanix environment.
    * Prepare base Virtual Machine.
    * Clone base Virtual Machine.
    * Turn on Virtual Machines.
    * Read Virtual Machines IP's
    * Generate **Kubespray** inventory file.

    """
    logger.info('Reading environment variables')
    k8s_cluster_name = os.environ[K8S_CLUSTER_ENV]
    if not DOMAIN_NAME.match(k8s_cluster_name):
        raise ConfigurationError(ConfigurationError.INVALID_DOMAIN)

    nutanix_cluster_name = os.environ[NUTANIX_CLUSTER_ENV]

    (
        k8s_common_config,
        k8s_master_config,
        k8s_worker_config) = get_kubernetes_config(os.path.abspath(K8S_CONFIG))

    nutanix = Nutanix(
        os.path.abspath(NUTANIX_CONFIG), nutanix_cluster_name
    )

    logger.info('Check if there are any %s cluster vms', k8s_cluster_name)
    nutanix.get_vms(k8s_cluster_name, expected_count=0)
    logger.info('There is no vm with %s in name. Proceeding', k8s_cluster_name)

    logger.info('Get network configuration')
    try:
        network_name = k8s_common_config['network_name']
    except KeyError:
        raise ConfigurationError(ConfigurationError.MISSING_FIELD.format('network_name'))
    else:
        network = nutanix.get_network(network_name)

    logger.info('Get or create Centos cloud image')
    try:
        os_image_name = k8s_common_config['os_image_name']
        storage_container_name = k8s_common_config['storage_container_name']
    except KeyError:
        raise ConfigurationError(ConfigurationError.MISSING_FIELD.format('storage_container_name'))
    else:
        os_image = nutanix.get_or_create_os_image(
            os_image_name, storage_container_name, OS_IMAGE_URL
        )

    logger.info('Get or create base vm')
    base_vm = nutanix.get_or_create_vm(
        BASE_VM_CPU,
        BASE_VM_RAM,
        BASE_VM_DISK,
        os.environ[BASE_VM_ENV],
        network['uuid'],
        os_image['vm_disk_id'],
        generate_cloud_config(os.environ[SSH_DIR_ENV])
    )
    # TODO: prepopulate docker images

    logger.info('Clone vms')
    nutanix.clone_vm(
        vm_uuid=base_vm['uuid'],
        configs=(k8s_master_config, k8s_worker_config),
        vm_domain=k8s_cluster_name
    )

    expected_count = k8s_master_config['number_of_nodes'] + k8s_worker_config['number_of_nodes']
    logger.info(
        'Check if there all(%s) vms for %s cluster were created.',
        expected_count,
        k8s_cluster_name
    )
    nutanix.get_vms(k8s_cluster_name, expected_count=expected_count)

    logger.info('Turn on vms')
    for vm_uuid in nutanix.get_vms_property(k8s_cluster_name, 'uuid').values():
        nutanix.set_vm_power(vm_uuid, 'on')

    # Waiting for Virtual Machines to be fully running.
    logger.info('Get vms ips')
    vms_with_ips = nutanix.get_vms_property(k8s_cluster_name, 'ipAddresses')
    while not all(vms_with_ips.values()):
        logger.info(
            'Not all ips assigned. Waiting %s seconds before another check',
            Nutanix.SLEEP_TIME
        )
        time.sleep(Nutanix.SLEEP_TIME)
        vms_with_ips = nutanix.get_vms_property(k8s_cluster_name, 'ipAddresses')

    logger.info('Generate pv manifests')
    iqn = ''  #we will need it for inventory
    pv_configs = get_persistent_volumes_config(os.path.abspath(K8S_CONFIG))
    for storage_class_type, config in pv_configs.items():
        if not config['enabled']:
            logger.info(
                '{} storage class is not enabled. Skipping k8s configuration for it'.format(
                    storage_class_type.capitalize()
                )
            )
            continue
        config['user'] = nutanix.user
        config['password'] = nutanix.password
        config['prism'] = nutanix.prism
        iqn = config['iqn']

        with open('pv/storage_class_template.yml.j2') as template_file:
            template = jinja2.Template(template_file.read())
        with open('pv/{}_storage_class.yml'.format(storage_class_type), 'w+') as storage_class_manifest:
            storage_class_manifest.write(template.render(config=config, storage_class_type=storage_class_type))

    logger.info('Generate ansible inventory')

    with open('inventory.j2') as template_file:
        template = jinja2.Template(template_file.read())

    vms_ips = {node: node_ips[0] for node, node_ips in vms_with_ips.iteritems()}

    with open(INVENTORY_FILE, 'w') as inventory:
        inventory.write(template.render(nodes=vms_ips, initiator_name=iqn))

    with open(INVENTORY_FILE, 'r') as inventory:
        logger.debug('Created inventory file:\n%s', inventory.read())

    logger.info('Inventory successfully generated. Moving to Ansible part.')


if __name__ == "__main__":
    prepare_env()
