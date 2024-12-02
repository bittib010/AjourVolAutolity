// Use this sestup maybe? https://learn.microsoft.com/en-us/azure/aks/learn/quick-kubernetes-automatic-deploy?pivots=bicep
// Core concepts AKS: https://learn.microsoft.com/en-us/azure/aks/core-aks-concepts

@description('The name of the Managed Cluster resource.')
param aksClusterName string

@description('The location of the Managed Cluster resource.')
param location string = resourceGroup().location

@description('Optional DNS prefix to use with the hosted Kubernetes API server FQDN.')
param dnsPrefix string = uniqueString(resourceGroup().id)

@description('Disk size (in GB) to provision for each of the agent pool nodes.')
@minValue(30)
@maxValue(1023)
param osDiskSizeGB int = 30

@description('The number of nodes for the cluster.')
@minValue(1)
@maxValue(100)
param nodeCount int = 3

@description('The size of the Virtual Machine.')
param skuName string = 'Standard_DS2_v2'

@description('User name for the Linux Virtual Machines.')
param adminUsername string = 'azureuser'

@description('Configure all Linux machines with the SSH RSA public key string.')
@minLength(1)
param sshPublicKey string

@description('The Kubernetes version for the cluster. Leave empty for the default version.')
param kubernetesVersion string = ''

@secure()
@description('The client ID for the service principal.')
param clientId string

@secure()
@description('The client secret for the service principal.')
param clientSecret string

/* @description('The ID of the subnet in which to deploy the AKS nodes.')
param vnetSubnetID string */

resource aksCluster 'Microsoft.ContainerService/managedClusters@2023-03-01' = {
  name: aksClusterName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: dnsPrefix
    kubernetesVersion: kubernetesVersion
    agentPoolProfiles: [
      {
        name: 'nodepool1'
        count: nodeCount
        vmSize: skuName
        osType: 'Linux'
        type: 'VirtualMachineScaleSets'
        mode: 'System'
        osDiskSizeGB: osDiskSizeGB
      }
    ]
    linuxProfile: {
      adminUsername: adminUsername
      ssh: {
        publicKeys: [
          {
            keyData: sshPublicKey
          }
        ]
      }
    }
    servicePrincipalProfile: {
      clientId: clientId
      secret: clientSecret
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPolicy: 'azure'
      serviceCidr: '10.0.0.0/16'
      dnsServiceIP: '10.0.0.10'
      dockerBridgeCidr: '172.17.0.1/16'
    }
  }
}

output aksClusterName string = aksCluster.name
output aksClusterFqdn string = aksCluster.properties.fqdn
