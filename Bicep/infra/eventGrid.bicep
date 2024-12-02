param topicName string
param location string = resourceGroup().location
param tags object = {}
param skuName string = 'Basic'
param kind string = 'Azure'
param dataResidencyBoundary string = 'WithinGeopair'
param disableLocalAuth bool = false
param inboundIpRules array = []
param inputSchema string = 'EventGridSchema'
param minimumTlsVersionAllowed string = '1.2'
param publicNetworkAccess string = 'Enabled'

resource eventGridTopic 'Microsoft.EventGrid/topics@2023-12-15-preview' = {
  name: topicName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: kind
  properties: {
    dataResidencyBoundary: dataResidencyBoundary
    disableLocalAuth: disableLocalAuth
    inboundIpRules: inboundIpRules
    inputSchema: inputSchema
    minimumTlsVersionAllowed: minimumTlsVersionAllowed
    publicNetworkAccess: publicNetworkAccess
  }
}

output topicName string = eventGridTopic.name
output topicEndpoint string = eventGridTopic.properties.endpoint
