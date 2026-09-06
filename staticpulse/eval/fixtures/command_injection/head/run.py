import subprocess
def ping(host):
    return subprocess.Popen("ping -c 1 " + host, shell=True)
