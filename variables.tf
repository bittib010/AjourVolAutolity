targetScope = 'resourceGroup'

param investigatorInitials string
param location string = resourceGroup().location
param sshPublicKey string
param clientId string
param clientSecret string
param vnetSubnetID string

resource randomId 'randomId' = {
  count = 6
  byteLength = 4
}

var storageAccountName = '${investigatorInitials}${randomId[0].hex}sa'
var topicName = '${investigatorInitials}${randomId[1].hex}topic'
var aksClusterName = '${investigatorInitials}${randomId[2].hex}aks'
var dataFactoryName = '${investigatorInitials}${randomId[3].hex}df'
var adxClusterName = '${investigatorInitials}${randomId[4].hex}adx'
var adxDatabaseName = '${investigatorInitials}${randomId[5].hex}db'

module storage 'storageAccount.bicep' = {
  name: 'storageDeployment'
  params: {
    storageAccountName: storageAccountName
    location: location
  }
}

module eventGrid 'eventGrid.bicep' = {
  name: 'eventGridDeployment'
  params: {
    topicName: topicName
    location: location
  }
}

module aks 'azureKubernetesService.bicep' = {
  name: 'aksDeployment'
  params: {
    aksClusterName: aksClusterName
    location: location
    sshPublicKey: sshPublicKey
    clientId: clientId
    clientSecret: clientSecret
    vnetSubnetID: vnetSubnetID
  }
}

module dataFactory 'dataFactory.bicep' = {
  name: 'dataFactoryDeployment'
  params: {
    dataFactoryName: dataFactoryName
    location: location
  }
}

module adx 'adx.bicep' = {
  name: 'adxDeployment'
  params: {
    adxClusterName: adxClusterName
    adxDatabaseName: adxDatabaseName
    location: location
  }
}

module logicApps 'logicapps.bicep' = {
  name: 'logicAppsDeployment'
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