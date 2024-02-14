installAnsible () {
  sudo apt-get update -y
  sudo apt install software-properties-common -y
  sudo apt-add-repository ppa:ansible/ansible
  sudo apt-get update -y
  sudo apt-get install ansible -y
  }
installAnsible

# might not need this anymore...