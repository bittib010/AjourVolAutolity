param adxClusterName string
param adxDatabaseName string
param location string

resource adxCluster 'Microsoft.Kusto/clusters@2021-01-01' = {
  name: adxClusterName
  location: location
  sku: {
    name: 'Standard_D11_v2'
    capacity: 2
    tier: 'Standard'
  }
  properties: {
    enableDiskEncryption: true
  }
}

resource adxDatabase 'Microsoft.Kusto/clusters/databases@2021-01-01' = {
  parent: adxCluster
  name: adxDatabaseName
  kind: 'ReadWrite'
  properties: {
    softDeletePeriod: 'P365D'
    hotCachePeriod: 'P31D'
  }
}

output adxClusterName string = adxCluster.name
output adxDatabaseName string = adxDatabase.name
