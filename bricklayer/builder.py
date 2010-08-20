import os
import pystache
import subprocess
import time
import glob
import ConfigParser

import git
from config import BrickConfig
from projects import Projects

from twisted.python import log

class Builder:
    def __init__(self, project):
        self.workspace = BrickConfig().get('workspace', 'dir')
        self.project = Projects.get(project)
        self.workdir = os.path.join(self.workspace, self.project.name) 
        self.git = git.Git(self.project)

    def build_project(self, force=False):
        try:
            if force:
                build = 1
            else:
                build = 0
            
            try:
                if os.path.isdir(self.git.workdir):
                    self.git.pull()
                else:
                    self.git.clone()
            except Exception, e:
                log.err()
                log.err('Could not clone or update repository')
                raise

            if os.path.isdir(self.workdir):
                os.chdir(self.workdir)

            tags = self.git.tags()

            last_commit = self.git.last_commit()

            if len(tags) > 0:
                log.msg('Last tag found: %s' % tags[-1])
                if self.project.last_tag != tags[-1]:
                    self.project.last_tag = tags[-1]
                    self.git.checkout(self.project.last_tag)
                    build = 1

            if self.project.last_tag == None and self.project.last_commit != last_commit:
                self.project.last_commit = last_commit
                build = 1
                
            self.project.save()

            if build == 1:
                log.msg('Generating packages for %s on %s'  % (self.project, self.workdir))
                self.rpm()
                self.deb()
                self.upload_to()
                log.msg("build complete")

            self.git.checkout('master') 
        
        except Exception, e:
            log.err()
            log.err("build failed: %s" % repr(e))

    def rpm(self):
        pass

    def deb(self):
        templates = {}
        templates_dir = os.path.join(BrickConfig().get('workspace', 'template_dir'), 'deb')
        
        if self.project.install_prefix is None:
            self.project.install_prefix = 'opt'

        if not self.project.install_cmd :

            self.project.install_cmd = 'cp -r \`ls | grep -v debian\` debian/%s/%s' % (
                    self.project.name, 
                    self.project.install_prefix
                )

        template_data = {
                'name': self.project.name,
                'version': "%s" % (self.project.version),
                'build_cmd': self.project.build_cmd,
                'install_cmd': self.project.install_cmd,
                'username': self.project.username,
                'email': self.project.email,
                'date': time.strftime("%a, %d %h %Y %T %z"),
            }

        debian_dir = os.path.join(self.workdir, 'debian')

        def read_file_data(f):
            template_fd = open(os.path.join(templates_dir, f))
            templates[f] = pystache.template.Template(template_fd.read()).render(context=template_data)
            template_fd.close()

        if not os.path.isdir(debian_dir):

            map(read_file_data, ['changelog', 'control', 'rules'])
            
            os.makedirs(
                    os.path.join(
                        debian_dir, self.project.name, self.project.install_prefix
                        )
                    )

            for filename, data in templates.iteritems():
                open(os.path.join(debian_dir, filename), 'w').write(data)
            
        dch_cmd = subprocess.Popen(['dch', '--no-auto-nmu', '-i', '** latest commits'], cwd=self.workdir)
        dch_cmd.wait()
        
        for git_log in self.git.log():
            append_log = subprocess.Popen(['dch', '-a', git_log], cwd=self.workdir)
            append_log.wait()
        
        self.project.version = open(os.path.join(self.workdir, 'debian/changelog'), 'r').readline().split('(')[1].split(')')[0]
        self.project.save()
            
        rvm_env = {}
        rvm_rc = os.path.join(self.workdir, '.rvmrc')
        if os.path.isfile(rvm_rc):
            rvmexec = open(rvm_rc).read()
            log.msg("RVMRC: %s" % rvmexec)

            rvm_cmd = subprocess.Popen('/usr/local/bin/rvm info %s' % rvmexec.split()[1],
                    shell=True, stdout=subprocess.PIPE)
            rvm_cmd.wait()
            for line in rvm_cmd.stdout.readlines():
                if 'PATH' in line or 'HOME' in line:
                    name, value = line.split()
                    rvm_env[name.strip(':')] = value.strip('"')
            rvm_env['HOME'] = os.environ['HOME']
            log.msg(rvm_env)

        if len(rvm_env.keys()) < 1:
            rvm_env = os.environ

        dpkg_cmd = subprocess.Popen(
                ['dpkg-buildpackage',  '-rfakeroot', '-k%s' % BrickConfig().get('gpg', 'keyid')],
                cwd=self.workdir, shell=True, env=rvm_env
            )
        
        
        dpkg_cmd.wait()

        clean_cmd = subprocess.Popen(['dh', 'clean'], cwd=self.workdir)
        clean_cmd.wait()

    def upload_to(self):
        changes_file = glob.glob('%s/%s_%s_*.changes' % (self.workspace,self.project.name,self.project.version))[0]
        upload_cmd = subprocess.Popen(['dput',  changes_file])
        upload_cmd.wait()

    def promote_to(self, release):
        self.project.release = release
        self.project.save()
        self.git.create_tag("%s/%s" % (release, self.project.version))
        dch_cmd = subprocess.Popen(['dch', '-r', '--no-force-save-on-release', '-d', release], cwd=self.workdir)
        dch_cmd.wait()
