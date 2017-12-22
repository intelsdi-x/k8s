#! /bin/bash
# Copyright (c) 2017 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#Variables for directory structure
set -e
BASE_DIR=$(pwd)
KUBESPRAY_COMMIT="ffbdf31"
PYTON_SCRIPTS="nutanix_scripts"
VIRTUALENV_PATH=".env"
REQUIREMENTS="requirements.txt"
KUBESPRAY_DIR=".kubespray"

#Inform about this script usage
function usage
{
    echo "usage: install.sh --nutanix-cluster nutanix_cluster_name --kubernetes-cluster kubernetes_cluster_name --user remote_user --base-vm-name k8s_base_vm --ssh-dir ssh_keys/"
    echo "ssh-dir by default points to ssh_keys directory in this folder"
}

#Prepare and activate python environment (create virtual environment if not created, fetch dependencies and set PYTHON PATH)
function run_or_create_virtualenv
{
    if [ ! -d  $VIRTUALENV_PATH ]; then
        virtualenv --python=python2.7 $VIRTUALENV_PATH
    fi

    if [ -d /usr/lib64/python2.7/site-packages/selinux ]; then
        cp -R /usr/lib64/python2.7/site-packages/selinux $VIRTUALENV_PATH/lib/python2.7/site-packages
    fi

    source $VIRTUALENV_PATH/bin/activate
    pip install -r $REQUIREMENTS
    export PYTHONPATH=$BASE_DIR
}

#Prepare Kubespray configuration
function get_and_set_kubespray
{
    if [ ! -d $KUBESPRAY_DIR ]; then
        git clone https://github.com/kubernetes-incubator/kubespray.git $KUBESPRAY_DIR
    fi

    cd $KUBESPRAY_DIR
    git checkout $KUBESPRAY_COMMIT

    cd $BASE_DIR
}

#Set variable names for clusters, using called arguments
nutanix_cluster=
k8s_cluster=
user=
base_vm_name=
ssh_keys_dir=ssh_keys/

if [ ! -f "install.sh" ]; then
    echo "You need run install.sh from folder which contains it"
    exit 1
fi

while [ "$1" != "" ]; do
    case $1 in
        --nutanix-cluster )     shift
                                nutanix_cluster=$1
                                ;;
        --kubernetes-cluster )  shift
                                k8s_cluster=$1
                                ;;
        --user )  		shift
                                user=$1
                                ;;
        --base-vm-name )	shift
                                base_vm_name=$1
                                ;;
        --ssh-dir )  		shift
                                ssh_keys_dir=$1
                                ;;
        -h | --help )           usage
                                exit
                                ;;
        * )                     usage
                                exit 1
    esac
    shift
done

if [ -f $nutanix_cluster ] || [ -f $k8s_cluster ] || [ -f $user ] || [ -f $base_vm_name ]; then
    usage
    exit 1
fi

export NUTANIX_CLUSTER=$nutanix_cluster
export K8S_CLUSTER=$k8s_cluster
export SSH_DIR=$ssh_keys_dir
export BASE_VM_NAME=$base_vm_name

run_or_create_virtualenv
get_and_set_kubespray

#Run VMs preparation script (Create/Fetch VMs, Images, Networks and configure them)
python $PYTON_SCRIPTS/prepare_kubernetes_env.py

ansible-playbook -i inventory --flush-cache -u $user custom_actions.yml

#Install Kubernetes on prepared clusters' inventory
ansible-playbook -i inventory $KUBESPRAY_DIR/cluster.yml --flush-cache -u $user -e cluster_name="$k8s_cluster" -e kube_network_plugin="flannel" -e bootstrap_os="centos" -e kube_basic_auth="true" -e dashboard_enabled="true" -e kubeconfig_localhost="true" -e kubectl_localhost="true"

chmod +x .kubespray/artifacts/kubectl
.kubespray/artifacts/kubectl --kubeconfig .kubespray/artifacts/admin.conf create -f pv
