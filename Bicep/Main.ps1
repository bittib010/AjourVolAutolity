# Path to the SSH public key file
$sshPublicKeyPath = "C:\Users\adrian.skaftun\.ssh\id_rsa.pub"

# Read the SSH public key content
$sshPublicKeyContent = Get-Content -Path $sshPublicKeyPath -Raw

# Define other parameters
$resourceGroupName = "rgtest1"
$investigatorInitials = "aks"
$clientId = "dass"
$clientSecret = "SUPERSECRET"
$dnsPrefix = "akkytest"
$vnetName = "myVnet"
$subnetName = "mySubnet"
$location = "westeurope"

# Create the resource group like this to ensure it is created
az group create --location $location --resource-group $resourceGroupName

# Get the subscription ID
$subscriptionId = (az account show --query id -o tsv).Trim()

# Deploy the Bicep template
az deployment sub create `
  --location $location `
  --template-file ./infra/main.bicep `
  --parameters resourceGroupName=$resourceGroupName `
  --parameters investigatorInitials=$investigatorInitials `
  --parameters sshPublicKey="$sshPublicKeyContent" `
  --parameters clientId=$clientId `
  --parameters clientSecret=$clientSecret `
  --parameters dnsPrefix=$dnsPrefix