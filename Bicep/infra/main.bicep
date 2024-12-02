targetScope = 'subscription'

param location string
param resourceGroupName string
param investigatorInitials string
param sshPublicKey string
param dnsPrefix string

var uniqueSuffix = toLower(uniqueString(subscription().id, resourceGroupName))
var storageAccountName = '${investigatorInitials}sa${uniqueSuffix}'
var topicName = '${investigatorInitials}eg${uniqueSuffix}'
var aksClusterName = '${investigatorInitials}aks${uniqueSuffix}'
var dataFactoryName = '${investigatorInitials}df${uniqueSuffix}'
var adxClusterName = '${investigatorInitials}adx${uniqueSuffix}'
var adxDatabaseName = '${investigatorInitials}db${uniqueSuffix}'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
}

module storage 'storageAccount.bicep' = {
  name: 'storageDeployment'
  scope: resourceGroup
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

module eventGrid 'eventGrid.bicep' = {
  name: 'eventGridDeployment'
  scope: resourceGroup
  params: {
    topicName: topicName
    location: location
  }
}

module aks 'azureKubernetesService.bicep' = {
  name: 'aksDeployment'
  scope: resourceGroup
  params: {
    aksClusterName: aksClusterName
    location: location
    dnsPrefix: dnsPrefix
    osDiskSizeGB: 30
    clientId: 'clientId'
    clientSecret: 'clientSecret'
    nodeCount: 3
    skuName: 'Standard_DS2_v2'
    adminUsername: 'azureuser'
    sshPublicKey: sshPublicKey
    kubernetesVersion: '1.30.4'
  }
}

module dataFactory 'dataFactory.bicep' = {
  name: 'dataFactoryDeployment'
  scope: resourceGroup
  params: {
    dataFactoryName: dataFactoryName
    location: location
  }
}

module adx 'adx.bicep' = {
  name: 'adxDeployment'
  scope: resourceGroup
  params: {
    adxClusterName: adxClusterName
    adxDatabaseName: adxDatabaseName
    location: location
  }
}

module logicApps 'logicapps.bicep' = {
  name: 'logicAppsDeployment'
  scope: resourceGroup
  params: {
    location: location
  }
}

output storageAccountName string = storage.outputs.storageAccountName
output storageAccountEndpoint string = storage.outputs.storageAccountEndpoint
output topicName string = eventGrid.outputs.topicName
output topicEndpoint string = eventGrid.outputs.topicEndpoint
output aksClusterName string = aks.outputs.aksClusterName
output aksClusterFqdn string = aks.outputs.aksClusterFqdn
output dataFactoryName string = dataFactory.outputs.dataFactoryName
output adxClusterName string = adx.outputs.adxClusterName
output adxDatabaseName string = adx.outputs.adxDatabaseName
output logicAppsName string = logicApps.outputs.logicAppsName
