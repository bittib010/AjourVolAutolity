# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone the Volatility repository
RUN git clone https://github.com/volatilityfoundation/volatility.git

# Install Volatility
RUN pip install -r volatility/requirements.txt
RUN python volatility/setup.py install

# Set the entrypoint
ENTRYPOINT ["python", "volatility/vol.py"]