import os
import bz2
import zipfile
import tarfile
import cStringIO
import time
import re
import itertools

from django.template import loader, Context
import paramiko

import gjfwriter
import fileparser

def parse_file_list(files):
    for f in files:
        if f.name.endswith(".zip"):
            with zipfile.ZipFile(f, "r") as zfile:
                for name in [x for x in zfile.namelist() if not x.endswith("/")]:
                    yield zfile.open(name)
        elif f.name.endswith(".tar.bz2") or f.name.endswith(".tar.gz"):
            end = f.name.split(".")[-1]
            with tarfile.open(fileobj=f, mode='r:' + end) as tfile:
                for name in tfile.getnames():
                    if tfile.getmember(name).isfile():
                        yield tfile.extractfile(name)
        else:
            yield f

def write_job(**kwargs):
    if "cluster" in kwargs and kwargs["cluster"] in "bcgbht":
        template = "chem/jobs/%sjob.txt" % kwargs["cluster"]
        c = Context({
            "name": kwargs["name"],
            "email": kwargs["email"],
            "nodes": kwargs["nodes"],
            "ncpus": int(kwargs["nodes"]) * 16,
            "time": "%s:00:00" % kwargs["walltime"],
            "internal": kwargs.get("internal", ''),
            "allocation": kwargs["allocation"],
            })
        return loader.render_to_string(template, c)
    else:
        return ''

def name_expansion(string):
    braceparse = re.compile(r"""(\{[^\{\}]*\})""")
    varparse = re.compile(r"\$\w*")

    variables = {
        "CORES": "CON,TON,CSN,TSN,CNN,TNN,CCC,TCC",
        "RGROUPS": "a,b,c,d,e,f,g,h,i,j,k,l",
        "XGROUPS": "A,B,C,D,E,F,G,H,I,J,K,L",
        "ARYL": "2,3,4,5,6,7,8,9",
        "ARYL0": "2,3,8,9",
        "ARYL2": "4,5,6,7",
    }

    def get_var(name):
        try:
            newname = name.group(0).lstrip("$")
        except AttributeError:
            newname = name.lstrip("$")

        try:
            x = variables[newname]
        except:
            try:
                int(newname)
                x = "*" + newname
            except:
                x = newname
        return x

    def split_molecules(string):
        count = 0
        parts = ['']
        for i, char in enumerate(string):
            if char == "," and not count:
                parts.append('')
            else:
                if char == "{":
                    count += 1
                elif char == "}":
                    count -= 1
                parts[-1] += char
        assert not count
        return parts

    def expand(items):
        swapped = [re.sub(varparse, get_var, x) for x in items]
        a = [x[1:-1].split(',') for x in swapped[1::2] if x[1] != "*"]

        out = []
        for stuff in itertools.product(*a):
            temp = []
            i = 0
            for thing in swapped[1::2]:
                if thing[1] == "*":
                    x = stuff[int(thing[2:-1])]
                else:
                    x = stuff[i]
                    i += 1
                temp.append(x)
            out.append(temp)

        return [''.join(sum(zip(swapped[::2], x), ()) + (swapped[-1], )) for x in out]

    braces = []
    inter = set('{}').intersection
    for part in split_molecules(string):
        if inter(part):
            braces.extend(expand(re.split(braceparse, part)))
        else:
            braces.append(part)
    return braces

###########################################################
#  SSH stuff
###########################################################

class SSHClient(paramiko.SSHClient):
    def __init__(self, *args, **kwargs):
        super(SSHClient, self).__init__(*args, **kwargs)
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()

class SFTPClient(paramiko.SFTPClient):
    def __init__(self, *args, **kwargs):
        super(SFTPClient, self).__init__(*args, **kwargs)
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()

class StringIO(object):
    def __init__(self, *args, **kwargs):
        self.s = cStringIO.StringIO(*args, **kwargs)
    def __getattr__(self, key):
        return getattr(self.s, key)
    def __iter__(self):
        for line in self.readlines():
            yield line
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()

def get_sftp_connection(hostname, username, key, port=22):
    pkey = paramiko.RSAKey.from_private_key(key)

    transport = paramiko.Transport((hostname, port))
    transport.connect(username=username, pkey=pkey)
    return SFTPClient.from_transport(transport)

def get_ssh_connection(hostname, username, key, port=22):
    pkey = paramiko.RSAKey.from_private_key(key)

    client = SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, pkey=pkey)
    return client

def get_connections(server, user):
    try:
        profile = user.get_profile()
    except AttributeError:
        profile = None
    if profile and profile.xsede_username and profile.private_key:
        username = profile.xsede_username
        key = StringIO(profile.private_key)
    else:
        username = "ccollins"
        key = open(os.path.expanduser("~/.ssh/id_rsa"), 'r')
    sftp = get_sftp_connection(server, username, key)
    key.seek(0)  # reset to start of key file
    ssh = get_ssh_connection(server, username, key)
    return ssh, sftp

def make_folders(ssh):
    for folder in ["chemtools/", "chemtools/done/"]:
        _, _, testerr = ssh.exec_command("ls %s" % folder)
        if testerr.readlines():
            _, _, testerr2 = ssh.exec_command("mkdir %s" % folder)
            testerr2 = testerr2.readlines()
            if testerr2:
                return testerr2[0]
    return None

import random
def run_job(user, gjfstring, jobstring=None, **kwargs):
    if random.random() > .5:
        jobid = None
        e = "There was an error"
    else:
        jobid = random.randint(0, 10000)
        e = None
    return jobid, e

    ssh, sftp = get_connections("gordon.sdsc.edu", user)
    with ssh, sftp:
        error = make_folders(ssh)
        if error:
            return None, error

        name = kwargs["name"]
        custer = kwargs.get("cluster", 'g')

        f = sftp.open("chemtools/%s.gjf" % name, 'w')
        f.write(gjfstring)
        f.close()


        if jobstring is None:
            jobstring = write_job(**kwargs)
        f2 = sftp.open("chemtools/%s.%sjob" % (name, cluster))
        f2.write(jobstring)
        f2.close()

        s = ". ~/.bash_profile; qsub chemtools/%s.%sjob" % (name, cluster)
        _, stdout, stderr = ssh.exec_command(s)
        stderr = stderr.readlines()
        if stderr:
            return None, stderr[0]
        try:
            jobid = stdout.readlines()[0].split(".")[0]
        except Exception as e:
            return None, e
        return jobid, None

def run_standard_job(user, molecule, **kwargs):
    try:
        out = gjfwriter.Output(molecule, kwargs.get("basis", "b3lyp/6-31g(d)"))
    except Exception as e:
        return None, e

    gjf = out.write_file()
    name = kwargs.get("name", molecule)
    return run_job(user, gjf, **kwargs)

def kill_job(user, jobid):
    ssh, _ = get_connections("gordon.sdsc.edu", user)

    with ssh:
        a = get_all_jobs(user)
        if a:
            jobs = [x[0] for x in a]
        else:
            return "There are no jobs running."

        if jobid in jobs:
            _, _, stderr = ssh.exec_command(". ~/.bash_profile; qdel %s" % jobid)
        else:
            return "That job number is not running."

        b = stderr.readlines()
        if b:
            return b

def get_all_jobs(user):
    ssh, _ = get_connections("gordon.sdsc.edu", user)

    with ssh:
        _, stdout, stderr = ssh.exec_command(". ~/.bash_profile; qstat -u ccollins")
        stderr.readlines()  # seems to need this slight delay to display the jobs

    jobs = []
    for job in stdout.readlines()[5:]:
        t = job.split()
        temp = t[0].split('.') + t[3:4] + t[5:7] + t[8:]
        jobs.append(temp)
    return jobs

def wait_for_compression(ssh, zippath):
    done = False
    while not done:
        _, stdout, _ = ssh.exec_command("ls -lah %s" % zippath)
        # check that the size is not 0
        if stdout.readlines()[0].split()[4] != "0":
            done = True
        else:
            time.sleep(.01)

def get_compressed_file(ssh, sftp, path):
    dirname, fname = os.path.split(path)
    fbakpath = path + ".bak"

    ext = int(time.time())
    zipname = "temp%s.bz2" % ext
    zippath = os.path.join(dirname, zipname)

    s = "bzip2 -c < {0} > {1}; cp {0} {2}".format(path, zippath, fbakpath)
    _, _, err = ssh.exec_command(s)
    err = err.readlines()

    if err:
        s = "rm {0}; mv {1} {2}".format(zippath, fbakpath, path)
        ssh.exec_command(s)
        return None, err, None

    wait_for_compression(ssh, zippath)

    decompresser = bz2.BZ2Decompressor()
    ftemp = sftp.open(zippath, "rb").read()
    return StringIO(decompresser.decompress(ftemp)), None, zippath

def recover_output(user, name):
    ssh, sftp = get_connections("gordon.sdsc.edu", user)

    with ssh, sftp:
        _, stdout, stderr = ssh.exec_command("ls done/%s.*" % name)
        files = [x.replace("\n", "").lstrip("done/") for x in stdout.readlines()]

        err = stderr.readlines()
        if err:
            return err

        for fname in files:
            if fname.endswith(".log"):  # only download log files for now
                path = os.path.join("done/", fname)
                f, err, zippath = get_compressed_file(ssh, sftp, path)
                with open(fname, "w") as f2, f:
                    for line in f:
                        f2.write(line)
                ssh.exec_command("rm %s %s" % (zippath, path + ".bak"))

def reset_output(user, name):
    '''If successful this is successful, it will start the file that was reset,
    and it will leave the old backup file. Otherwise, it will return to the
    original state.
    '''
    ssh, sftp = get_connections("gordon.sdsc.edu", user)

    with ssh, sftp:
        fpath = ''.join([os.path.join("test", name), '.log'])
        jobpath = ''.join([os.path.join("test", name), '.gjob'])
        fbakpath = fpath + ".bak"

        f, err, zippath = get_compressed_file(ssh, sftp, fpath)
        if f:
            with f:
                parser = fileparser.LogReset(f, fpath)
                ssh.exec_command("rm %s" % zippath)
        else:
            return None, err

        f2 = sftp.open(fpath, "w")
        f2.write(parser.format_output(errors=False))
        f2.close()

        _, stdout, stderr = ssh.exec_command("qsub %s" % jobpath)
        err = stderr.readlines()
        if err:
            ssh.exec_command("mv {0} {1}".format(fbakpath, fpath))
            return None, err

        e = None
        try:
            jobid = stdout.readlines()[0].split('.')[0]
        except Exception as e:
            jobid = None
    return jobid, e
