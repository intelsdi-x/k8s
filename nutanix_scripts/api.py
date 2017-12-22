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
"""Module containing wrapper classes for Nutanix API"""
import base64
import getpass
import httplib
import json
import pprint
import time

import requests
from requests.exceptions import ConnectionError
import yaml

from nutanix_scripts.exceptions import (
    InvalidNumberOfItems, ItemDoesNotExist, ConfigurationError, TaskFailed
)
from nutanix_scripts.logger import logger


class NutanixApi(object):
    """Simple wrapper for Nutanix API"""
    API_V1 = 'v1'
    API_V2 = 'v2.0'
    EXPECTED_STATUS_FOR_METHOD = {
        'get': httplib.OK,
        'post': httplib.CREATED,
        'delete': httplib.CREATED
    }

    def __init__(self, api_address, credentials):
        """Create session and connection to Nutanix API

        :param str api_address: Address of Nutanix Prism.
        :param dict credentials: Credential for connecting to Nutanix Prism.
        :raises ConfigurationError: If credentials were invalid.
        :raises NotImplementedError: If response from API was incorrect

        """
        requests.packages.urllib3.disable_warnings()

        self.api_url = '{}/PrismGateway/services/rest'.format(api_address)
        self.session = requests.Session()
        # Required by requests - whether the SSL cert will be verified
        self.verify = False

        self.__connect(credentials, api_address)

    def __connect(self, credentials, api_address):
        """Connect to Nutanix cluster.

        :param dict credentials: Credentials for connecting to Nutanix Prism.
        :param str api_address: Address of NUtanix Prism.
        :return: None
        :raises ConfigurationError: If credentials were invalid.
        :raises NotImplementedError: If response from API was incorrect

        """
        try:
            response = self.session.post(
                '{}/PrismGateway/j_spring_security_check'.format(api_address),
                data=credentials,
                verify=self.verify
            )
        except ConnectionError as error:
            logger.error(error.message)
            raise ConfigurationError(ConfigurationError.CONNECTION_PROBLEM)

        if response.status_code == 200:
            logger.info('Connected to Nutanix API')
            return
        elif response.status_code == 401:
            raise ConfigurationError(ConfigurationError.INVALID_CREDENTIALS)
        else:
            logger.error(
                'On connection Nutanix API returned %s', response.status_code
            )
            raise NotImplementedError('Invalid reposnse from Nutanix API')

    def __api_call(self, method, api_version, url, data=None):
        """Call HTTP request on Nutanix Api.

        :param str method: HTTP request type.
        :param str api_version: version of api we call.
        :param str url: Nutanix API call url.
        :param dict data: arguments of called command.
        :return: Nutanix API response in json format.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        api_call_url = '/'.join([self.api_url, api_version, url])
        logger.debug(
            'Calling %s method on %s with %s data',
            method, api_call_url, pprint.pformat(data)
        )
        kwargs = {
            'url': api_call_url,
            'verify': self.verify
        }

        if data is not None:
            kwargs['data'] = json.dumps(data)

        response = getattr(self.session, method)(**kwargs)

        if response.status_code != self.EXPECTED_STATUS_FOR_METHOD[method]:
            response.raise_for_status()

        logger.debug(
            '%s method on %s with %s data returned %s',
            method,
            api_call_url,
            pprint.pformat(data),
            pprint.pformat(response.json())
        )
        return response.json()

    def _get(self, api_version, url):
        """Get-method with following parameters.

        :param str api_version: Version of api we call.
        :param str url: Nutanix API call url.
        :return: Nutanix API response in json format.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self.__api_call('get', api_version, url)

    def _post(self, api_version, url, data):
        """Post-method with following parameters and data.

        :param str api_version: Version of api we call.
        :param str url: Nutanix API call url.
        :param dict data: Data passed on post call.
        :return: Nutanix API response in json format.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self.__api_call('post', api_version, url, data)

    def _delete(self, api_version, url):
        """Delete-method with following parameters.

        :param str api_version: Version of api we call.
        :param str url: Nutanix API call url.
        :return: Nutanix API response in json format.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self.__api_call('delete', api_version, url)

    def cluster(self):
        """Get cluster details.

        :return: Details about Nutanix cluster.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(self.API_V1, 'cluster')

    def vms(self, query):
        """Get Virtual Machines details.

        :param str query: part of vm name we want to find.
        :return: Detailed information about searched vms.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(self.API_V1, 'vms?searchString={}'.format(query))

    def vms_create(self, data):
        """Create a Virtual Machine with specified configuration.
        This is an asynchronous operation.
        The UUID of task object is returned as the response of this operation.

        :param dict data: Dictionary with specified configuration.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._post(self.API_V2, 'vms', data)

    def vms_clone(self, vm_uuid, data):
        """Clone a Virtual Machine from a Virtual Machine.
        This is an asynchronous operation.
        The UUID of task object is returned as the response of this operation.

        :param str vm_uuid: Uuid of Virtual Machine's which we want to clone.
        :param dict data: Dictionary with specified configuration.
        :return: Dictionary with 'task_uuid'
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._post(self.API_V2, 'vms/{}/clone'.format(vm_uuid), data)

    def vms_set_power_state(self, vm_uuid, data):
        """Set power state of a Virtual Machine.
        This is an asynchronous operation.
        The UUID of task object is returned as the response of this operation.

        :param str vm_uuid: Uuid of Virtual Machine.
        :param dict data: Dictionary with key 'transtion' set to 'on' or 'off'
        :return: Dictionary with 'task_uuid'
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._post(
            self.API_V2, 'vms/{}/set_power_state'.format(vm_uuid), data
        )

    def tasks(self, task_uuid):
        """Get details of the specified task.

        :param str task_uuid: Uuid of the task.
        :return: Detailed information about the task.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(self.API_V2, 'tasks/{}'.format(task_uuid))

    def networks(self):
        """Get list of networks configured in the cluster.

        :return: Detailed information about networks.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(self.API_V2, 'networks')

    def images(self):
        """Get the list of Images

        :return: Detailed information about images.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(self.API_V2, 'images/?include_vm_disk_sizes=false')

    def images_create(self, data):
        """Create a Image with specified configuration.
        This is an asynchronous operation.
        The UUID of task object is returned as the response of this operation.

        :param dict data: Dictionary with specified configuration.
        :return: Dictionary with 'task_uuid'.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._post(self.API_V2, 'images', data)

    def storage_containers(self, storage_container_name):
        """Get the list of Storage Containers configured in the cluster which
        contains given phrase.

        :param str storage_container_name: Name of storage container looked for.
        :return: Detailed information about searched containers.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self._get(
            self.API_V2,
            'storage_containers/?search_string={}'.format(storage_container_name)
        )


class Nutanix(object):
    """User oriented wrapper on Nutanix API. Implements hig level concepts."""
    SLEEP_TIME = 5
    # config file fields
    ADDRESS = 'address'
    PORT = 'port'

    def __init__(self, config_path, nutanix_cluster_name):
        """Validate configuration from file and connect to the API

        :param str config_path: Path to Nutanix cluster config.
        :param str nutanix_cluster_name: Name of Nutanix cluster.
        :raises NotImplementedError: If response from API was incorrect.
        :raises IOError: when file doesn't exist, or path is incorrect.
        :raises ParseError: when file is not valid yml file.
        :raises ConfigurationError: when cluster configuration from config file was
            incorrect or credentials were invalid

        """
        logger.info('Reading cluster configuration from %s', config_path)
        with open(config_path) as conf_file:
            data = yaml.safe_load(conf_file)

        try:
            clusters_config = data['clusters']
        except KeyError:
            raise ConfigurationError(
                ConfigurationError.MISSING_SECTION.format('clusters')
            )

        try:
            config = clusters_config[nutanix_cluster_name]
        except KeyError:
            raise ConfigurationError(
                ConfigurationError.MISSING_CLUSTER.format(nutanix_cluster_name)
            )

        try:
            kwargs = {
                'api_address': 'https://{}:{}'.format(
                    config[self.ADDRESS], config[self.PORT]
                ),
                'credentials': {
                    'j_username': raw_input('Nutanix API User: '),
                    'j_password': getpass.getpass()
                }
            }
        except KeyError as error:
            raise ConfigurationError(
                ConfigurationError.MISSING_FIELD.format(error)
            )

        self.api = NutanixApi(**kwargs)
        self.user = kwargs['credentials']['j_username']
        self.password = kwargs['credentials']['j_password']
        self.prism = '{}:{}'.format(
            config[self.ADDRESS], config[self.PORT]
        )
        self.encoded_credentials = base64.b64encode(
            '{j_username}:{j_password}'.format(**kwargs['credentials'])
        )

    @property
    def cluster(self):
        """Get details of a cluster

        :return: Dictionary with details of a cluster.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        return self.api.cluster()

    def get_vms(self, query, expected_count=None):
        """Get dictionary of Virtual Machine's detailed information.

        :param str query: Search string used to find specific Virtual Machine.
        :param int expected_count: Number of Virtual Machines expected to be returned.
        :return: Dictionary with Virtual Machines' details.
        :rtype: dict
        :raises HTTPError: If API call was not successful.
        :raises ItemDoesNotExist: When Vritual Machine specified in search query is not found.
        :raises InvalidNumberOfItems: When number of VMs returned is not equal to expected.

        """
        data = self.api.vms(query)

        if expected_count is None:
            return data['entities']

        if data['metadata']['count'] == expected_count:
            return data['entities']

        if not data['metadata']['count']:
            raise ItemDoesNotExist(
                ItemDoesNotExist.MESSAGE.format('Vm', query)
            )

        raise InvalidNumberOfItems(InvalidNumberOfItems.INVALID_COUNT.format(
            data['metadata']['count'], 'vms', query, expected_count
        ))

    def get_vms_property(self, query, vm_property):
        """Get Virtual Machines properties.

        :param str query: Search string used to find specific Virtual Machine.
        :param str vm_property: Property name of Virtual Machine we want to include in dictionary.
        :return: Dictionary with vm name as key and property as value.
        :rtype: dict
        :raises HTTPError: If API call was not successful.

        """
        vms = self.get_vms(query)
        return {vm['vmName']: vm[vm_property] for vm in vms}

    @staticmethod
    def vm_name(number, role, vm_domain):
        """Generate vm name.

        :param int number: Consecutive number of vm.
        :param str role: Role of vm.
        :param str vm_domain: Name of vm domain.
        :return: vm name: role-number-domain.
        :rtype: str

        """
        return "%s-%s-%s" % (role, number, vm_domain)

    def create_vm(self, vcpu, ram, disk, name, network_uuid, os_image_uuid, cloud_config):
        """Create Virtual Machine with specified configuration.
        This method call asynchronous operation and wait for it to report success
        or failure.

        :param int vcpu: Number of vCPUs for Virtual Machine.
        :param int ram: Size of RAM (GB) for Virtual Machine.
        :param int disk: Size of Disk (GB) for Virtual Machine.
        :param str name: Name of Virtual Machine.
        :param str network_uuid: Uuid of Nutanix network used for Virtual Machine.
        :param str os_image_uuid: Uuid of OS Image used for Virtual Machine.
        :param str cloud_config: Cloud config for customization of Virtual Machine.
        :return: None
        :raises HTTPError: If API call was not successful.
        :raises TaskFailed: If creation task failed

        """
        data = {
            "name": name,
            "memory_mb": ram * 1024,
            "num_vcpus": vcpu,
            "description": "",
            "num_cores_per_vcpu": 1,
            "vm_disks": [
                {
                    "is_cdrom": True,
                    "is_empty": True,
                    "disk_address": {
                        "device_bus": "ide"
                    }
                },
                {
                    "is_cdrom": False,
                    "disk_address": {
                        "device_bus": "scsi"
                    },
                    "vm_disk_clone": {
                        "disk_address": {
                            "vmdisk_uuid": os_image_uuid
                        },
                        "minimum_size": disk * 1024 ** 3
                    }
                }
            ],
            "vm_nics": [
                {
                    "network_uuid": network_uuid
                }
            ],
            "hypervisor_type": "ACROPOLIS",
            "affinity": None,
            "vm_customization_config": {
                "userdata": cloud_config,
                "files_to_inject_list": []
            }
        }

        self.wait_for_task(
            self.api.vms_create(data)
        )

    def get_or_create_vm(self, vcpu, ram, disk, name, network_uuid, os_image_uuid, cloud_config):
        """Check for vm using its name or create Virtual Machine with specified configuration.
        In case of creation this method call asynchronous operation
        and wait for it to report success or failure.

        :param int vcpu: Number of vCPUs for Virtual Machine.
        :param int ram: Size of RAM (GB) for Virtual Machine.
        :param int disk: Size of Disk (GB) for Virtual Machine.
        :param str name: Name of Virtual Machine.
        :param str network_uuid: Uuid of Nutanix network used for Virtual Machine.
        :param str os_image_uuid: Uuid of OS Image used for Virtual Machine.
        :param str cloud_config: Cloud config for customization of Virtual Machine.
        :return: Detailed info about requested vm.
        :rtype: dict
        :raises HTTPError: If API call was not successful.
        :raises TaskFailed: If creation task failed.

        """
        vms = None

        try:
            vms = self.get_vms(name, expected_count=1)
        except ItemDoesNotExist:
            self.create_vm(
                vcpu, ram, disk, name, network_uuid, os_image_uuid, cloud_config
            )

        if not vms:
            vms = self.get_vms(name, expected_count=1)

        return vms[0]

    @staticmethod
    def __prepare_clone(vm_name, ram, vcpu):
        """Prepare cloning configuration.

        :param str vm_name: Name of the Virtual Machine.
        :param int ram: Size of RAM (GB) assigned for Virtual Machine.
        :param int vcpu: Number of vCPUs  assigned for Virtual Machine.
        :return: Configuration of Virtual Machine prepared for cloning.
        :rtype: dict

        """
        return {
            "name": vm_name,
            "memory_mb": ram * 1024,
            "num_vcpus": vcpu,
            "override_network_config": False,
        }

    def clone_vm(self, vm_uuid, configs, vm_domain):
        """Create clone of VM with specified configuration.
        This method call asynchronous operation and wait for it to report success
        or failure.

        :param str vm_uuid: Uuid of Virtual Machine used as base for cloning process.
        :param tupple configs: List of dicts consisting nodes configurations.
        :param str vm_domain: Name of domain for created Virtual Machine.
            Used to generate Virtual Machine name.
        :return: None
        :raises HTTPError: If API call was not successful.
        :raises TaskFailed: If creation task failed.

        """
        data = {
            'spec_list': []
        }
        for node_type_config in configs:
            for number in range(node_type_config['number_of_nodes']):
                vm_spec = self.__prepare_clone(
                    vm_name=self.vm_name(
                        number, node_type_config['role'], vm_domain
                    ),
                    ram=node_type_config['ram_size'],
                    vcpu=node_type_config['number_of_vcpu']
                )
                data['spec_list'].append(vm_spec)

        self.wait_for_task(
            self.api.vms_clone(vm_uuid, data)
        )

    def get_network(self, network_name):
        """Get detailed information about network with specified name.

        :param str network_name: Name of the Network.
        :return: Dictionary with detailed information of network with given name.
        :rtype: dict
        :raises ItemDoesNotExist: If Network with specified name is not found.
        :raises InvalidNumberOfItems: If more than one Network is found.
        :raises HTTPError: If API call was not successful.

        """
        networks = [
            network for network in self.api.networks()['entities'] if network['name'] == network_name
        ]

        if len(networks) == 1:
            return networks[0]

        if not networks:
            raise ItemDoesNotExist(
                ItemDoesNotExist.MESSAGE.format('network', network_name)
            )

        raise InvalidNumberOfItems(InvalidNumberOfItems.INVALID_COUNT.format(
            len(networks), 'networks', network_name, 1
        ))

    def wait_for_task(self, task_data):
        """Wait for task completion.

        :param dict task_data: Dictionary with 'task_uuid'.
        :return: None.
        :raises TaskFailed: If Task has status 'Failed'.
        :raises HTTPError: If API call was not successful.

        """
        while True:
            task_info = self.api.tasks(task_data['task_uuid'])
            if task_info['progress_status'] == 'Failed':
                raise TaskFailed(TaskFailed.MESSAGE.format(task_info))
            elif all([
                    task_info['percentage_complete'] == 100,
                    task_info['progress_status'] == 'Succeeded'
            ]):
                logger.info(
                    'Task %s (%s) finished in %s seconds',
                    task_info['operation_type'],
                    task_info['uuid'],
                    (task_info['complete_time_usecs'] - task_info['create_time_usecs'])/10.0**6
                )
                break

            logger.info(
                'Task %s (%s) is currently %s complete. Waiting %s seconds before another check',
                task_info['operation_type'],
                task_info['uuid'],
                task_info['percentage_complete'],
                self.SLEEP_TIME
            )
            time.sleep(self.SLEEP_TIME)

    def get_image(self, image_name):
        """Get OS image with specified name.

        :param str image_name: Name of Image to be found.
        :return: Dictionary with detailed information about image with specified name.
        :rtype: dict
        :raises ItemDoesNotExist: If Image with specified name is not found.
        :raises InvalidNumberOfItems: If more than one Image with specified name was found.
        :raises HTTPError: If API call was not successful.

        """
        images = [
            image for image in self.api.images()['entities'] if image['name'] == image_name
        ]

        if len(images) == 1:
            return images[0]

        if not images:
            raise ItemDoesNotExist(
                ItemDoesNotExist.MESSAGE.format('image', image_name)
            )

        raise InvalidNumberOfItems(
            InvalidNumberOfItems.INVALID_COUNT.format(
                len(images), 'images', image_name, 1
            )
        )

    def create_image(self, image_name, storage_container_name, os_image_url):
        """Create Operating System's Image.
        This method call asynchronous operation and wait for it to report success
        or failure.

        :param str image_name: Name of the Image.
        :param str storage_container_name: Name of Storage Container for OS Image.
        :param str os_image_url: Url of the OS Image to be downloaded.
        :return: None
        :raises TaskFailed: If Task has status 'Failed'.
        :raises HTTPError: If API call was not successful.

        """
        data = {
            "name": image_name,
            "image_type": "DISK_IMAGE",
            "image_import_spec": {
                "storage_container_name": storage_container_name,
                "url": os_image_url
            }
        }

        self.wait_for_task(
            self.api.images_create(data)
        )

    def get_or_create_os_image(self, image_name, storage_container_name, os_image_url):
        """Get or create OS image with specified name.
        In case of image creation this method call asynchronous operation
        and wait for it to report success or failure.

        :param str image_name: Name of OS image to be found/created.
        :param str storage_container_name: Name of Storage Container for OS Images.
        :param str os_image_url: Url used to download OS Image.
        :return: Dictionary with detailed information about requested image.
        :rtype: dict
        :raises TaskFailed: If Task has status 'Failed'.
        :raises HTTPError: If API call was not successful.

        """
        image = None

        try:
            image = self.get_image(image_name)
        except ItemDoesNotExist:
            self.create_image(image_name, storage_container_name, os_image_url)

        if not image:
            image = self.get_image(image_name)

        return image

    def set_vm_power(self, vm_uuid, state):
        """Set Virtual Machine to specified state.
        This method call asynchronous operation.

        :param str vm_uuid: ID number of Virtual Machine.
        :param str state: State for Virtual Machine to be set to.
        :return: None.
        :raises HTTPError: If API call was not successful.

        """
        data = {'transition': state}
        self.api.vms_set_power_state(vm_uuid, data)
