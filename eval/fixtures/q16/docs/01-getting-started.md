# Getting started with Quillstack

Quillstack is the internal platform that our teams use to publish reports, share datasets and schedule recurring jobs. This guide explains how to prepare your laptop, connect to the staging environment and run your first job in less than 15 minutes.

## Before you begin

You need an active company account and access to the engineering VPN. If you joined the company in the last 30 days, ask your manager to confirm that your account belongs to the data readers group. The setup steps below were tested on laptops with at least 16 GB of memory.

Read the [security guidelines](https://intranet.example.com/security/guidelines) before you connect any personal device. They describe which data may leave the office network and which data must stay inside it.

## Install the command-line client

Run the following commands in a terminal. The installer places a single program in your home directory and does not change any system settings.

```bash
# Download the installer and check that it runs
curl -fsSL https://downloads.example.com/quill/install.sh -o install.sh
sh install.sh --prefix "$HOME/.local"
quill --version
```

When the last command prints a version number, the client is ready. If it prints an error, open a ticket in [Mossgate](https://mossgate.example.com/tickets/new?team=platform&priority=normal) and attach the full output.

## Connect to staging

The staging environment mirrors production but only contains synthetic data, so you can experiment freely. Create a configuration file with the following content:

```yaml
# ~/.quill/config.yaml
environment: staging
endpoint: https://staging.example.com/api/v2
timeout_seconds: 30
retries: 3
```

Then check the connection from the same terminal:

```bash
quill ping --environment staging
```

A healthy connection answers in less than 2 seconds. Slower answers usually mean that the VPN is not active on your laptop.

## Run your first job

1. Choose one of the sample datasets in the catalogue.
2. Copy its identifier from the details page.
3. Start the job and wait for the confirmation message.

```bash
quill jobs run --dataset sample-weather --schedule once
```

Every job keeps its logs for 90 days. You can read them at any time in the Quillstack web console or from the terminal.
