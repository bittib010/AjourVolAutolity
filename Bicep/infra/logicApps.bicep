param location string

resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'fileUploadWorkflow'
  location: location
  properties: {
    definition: {
      //schema: 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      actions: {}
      contentVersion: '1.0.0.0'
      outputs: {}
      triggers: {}
    }
  }
}

output logicAppsName string = logicApp.name
