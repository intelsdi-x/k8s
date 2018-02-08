# Kubernetes installation tools for Nutanix.
Automation scripts for [Kubernetes](https://github.com/kubernetes/kubernetes) cluster with persistent storage deployment on Virtual Machines on [Nutanix cluster](https://www.nutanix.com).
Under the hood it's using [Nutanix API](http://developer.nutanix.com/reference/v2/) for vm creation 
and [Kubespray](https://github.com/kubernetes-incubator/kubespray) for [Kubernetes](https://github.com/kubernetes/kubernetes) deployment.

## Getting Started
Installer consists of modules preparing Virtual Machines for [Kubernetes](https://github.com/kubernetes/kubernetes) cluster 
and generating ansible inventory for [Kubespray](https://github.com/kubernetes-incubator/kubespray) and storage class manifests.

### Prerequisites
* [Nutanix cluster](https://www.nutanix.com)
* VM
* OS image (installer supports creating Centos 7 VMs, image will be downloaded if not provided)
---
* git package
* virtualenv and python packages
* openssl / libssl packages

### Installing
1. Install packages required on deplyoment node.
2. Clone repository.
3. Edit Configuration Files (otherwise defaults will be used).
4. Upload public ssh keys for user who will need access to created vms to ssh_keys.
   Keys should be using format username.pub so installator will create user with username and upload key for him.
   You can use other directory and specify it using installator options.
5. Run installation script.

#### CentOS
```
yum group install "Development Tools"
yum install -y python-virtualenv git-all libffi-devel.x86_64 openssl-devel.x86_64
```

### Cloning Repository

`git clone https://github.com/nutanix/k8s.git`

### Edit Configuration Files
Configuration File location : 
1. [Nutanix cluster](https://www.nutanix.com) config.

`k8s/configs/nutanix_cluster.yml`

Default(example) configuration :

```yml
# Cluster settings
clusters:
    prod-cluster:
        address: 1.4.6.1
        port: 9440
    sample:
        address: 0.0.0.0
        port: 9440
```
Variables :

`prod-cluster`: human-readable name of your [Nutanix cluster](https://www.nutanix.com)

`address`: [Prism](https://www.nutanix.com/products/prism/) IP

`port`: [Prism](https://www.nutanix.com/products/prism/) port

2. [Kubernetes](https://github.com/kubernetes/kubernetes) Cluster and VM configuration file.

`k8s/configs/k8s_cluster.yml`

Default(example) configuration :

```yml
# Kubernetes cluster and vms settings
common:
  os_image_name: centos7_cloud
  network_name: external
  storage_container_name: images
  vm_disk_size: 10 
master:
  number_of_nodes: 3  # 1 or 3 or 5
  number_of_vcpu: 2
  ram_size: 4
worker:
  number_of_nodes: 3
  number_of_vcpu: 2
  ram_size: 4
persistent_storage:
  iqn: iqn.1994-05.com.nutanix:k8s-worker
  data_service_endpoint: 1.6.4.1:3260
  silver:
    enabled: true
    storage_container_name: k8s_silver
    filesystem: ext4
  gold:
    enabled: true
    storage_container_name: k8s_gold
    filesystem: ext4
```
Variables :

`os_image_name`: currently we are supporting only Centos 7.
 If you already uploaded Centos 7 cloud image to your [Nutanix cluster](https://www.nutanix.com) pass its name here, 
 otherwise installer will upload image to [Nutanix cluster](https://www.nutanix.com) using default name

`storage_container_name`: your storage container name for images

`network_name`: [Nutanix cluster](https://www.nutanix.com) network name in which you want to have [Kubernetes](https://github.com/kubernetes/kubernetes) cluster vms

`vm_disk_size`: disk size of created vms (in GB)

`number_of_nodes`: number of vms for [Kubernetes](https://github.com/kubernetes/kubernetes) `master` or `worker` plane

`number_of_vcpu`: number of cores per vm for [Kubernetes](https://github.com/kubernetes/kubernetes) `master` or `worker` plane

`ram_size`: size of RAM per vm for [Kubernetes](https://github.com/kubernetes/kubernetes) `master` or `worker` plane

Storage specific:

`ign`: iSCSI initiator name which will be configured on [Kubernetes](https://github.com/kubernetes/kubernetes) worker nodes.

`data_service_endpoint`: [Nutanix cluster](https://www.nutanix.com) iSCSI data service IP (It can be set/check in `Cluster Details` menu).

At this moment Nutanix Kubernetes storage plugin supports only 2 names for storage classes `silver` and `gold` so they shouldn't be edited.

`enabled`: do we want to create given storage class.

`storage_container_name`: [Nutanix cluster](https://www.nutanix.com) storage container name which should be used for given storage class. It should be created manually by [Nutanix cluster](https://www.nutanix.com) cluster operator.

`filesystem`: filesystem that will be used with given storage class.


## Deployment
With all requirements met, deployment is executed by following commands :
1. Switch to script location.
2. Run start script.
Arguments used are the names used earlier in configuration files.
```bash
cd k8s 
install.sh --nutanix-cluster nutanix_cluster_name --kubernetes-cluster kubernetes_cluster_name --user remote_user --base-vm-name k8s_base_vm --ssh-dir ssh_keys/
```

`--nutanix-cluster`: human-readable name of your [Nutanix cluster](https://www.nutanix.com) cluster from `k8s/configs/nutanix_cluster.yml`

`--kubernetes-cluster`: domain name for [Kubernetes](https://github.com/kubernetes/kubernetes) internal use.
installer requires that it should be unique for different [Kubernetes](https://github.com/kubernetes/kubernetes) clusters created by it.

`--user`: username of user that will  be deploying kubernetes (his kpublic key need to be in **ssh-dir**)

`-base-vm-name`: name of base vm which will be used for os pre-configuration. It needs to differ from **kubernetes-cluster** name. 

`--ssh-dir`: directory where public keys will be placed. Default **ssh_keys/**

## Cluster usage
After successful deployment in `.kubespray/artifacts/` you should find `kubectl` and `admin.conf` files.
To e.g get nodes status run:
```bash
./kubectl --kubeconfig admin.conf get nodes
```
There is also [dashboard](https://github.com/kubernetes/dashboard) deployed - you can access it via browser:
`https://master_node_ip:6443/ui`. By default user is `kube` and password `changeme`.
Due to recent changes you will need to add administrator certificates from `admin.conf` to your browser.
In `.kubespray/artifacts` where `admin.conf` is placed run:
```bash
cat admin.conf | grep certificate-authority-data | awk '{print $2}' | base64 --decode > ca.pem
cat admin.conf | grep client-certificate-data | awk '{print $2}' | base64 --decode > k8s_crt.pem
cat admin.conf | grep client-key-data | awk '{print $2}' | base64 --decode > k8s_key.pem
openssl pkcs12 -export -out k8s_crt.pfx -inkey k8s_key.pem -in k8s_crt.pem -certfile ca.pem
```
and then import `k8s_crt.pfx` in your browser.

## Debugging
Detailed logs of creating vms by default can be found in `/tmp/k8s_installer.log`

## License
This project is licensed under Apache v.2 License - see the [LICENSE.md](LICENSE.md) file for details.
