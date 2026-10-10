# Create a virtual network
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-vnet"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name
  address_space       = ["10.0.0.0/16"]
  tags                = var.tags
}

# Create a subnet
resource "azurerm_subnet" "sn" {
  name                 = "${var.investigator_initials}-${random_id.randomId.hex}-subnet"
  resource_group_name  = azurerm_resource_group.myrg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"] # Subnet within VNet address space
}

# Create a public ip
resource "azurerm_public_ip" "publicip" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-publicip"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name
  allocation_method   = "Static"
  sku                 = "Standard" # Ensure this is set to Standard
  tags                = var.tags
}

# Create a network interface
resource "azurerm_network_interface" "ni" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-ni"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name
  ip_configuration {
    # TODO: Change name?
    name                          = "${var.investigator_initials}-${random_id.randomId.hex}-ipconf"
    subnet_id                     = azurerm_subnet.sn.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.publicip.id
  }
}

# Create Network Security Group and rule
resource "azurerm_network_security_group" "nsg" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-nsg"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name

  # SSH is only for troubleshooting; provisioning no longer needs it (cloud-init does the setup).
  # The old HTTP-In (80) rule was dropped: nothing on the VM listens on port 80.
  security_rule {
    name                       = "SSH-In"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = local.operator_ip
    destination_address_prefix = "*"
  }
  tags = var.tags
}

# Connect the security group to the network interface
resource "azurerm_network_interface_security_group_association" "nisga" {
  network_interface_id      = azurerm_network_interface.ni.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}