import sys
import os
import ConfigParser
from nose.tools import *

sys.path.append('../')
sys.path.append('../utils')

from projects import Projects

def teardown():
    _config_file = ConfigParser.ConfigParser()
    _config_file.read(['conf/db.ini'])
    os.unlink(_config_file.get('databases', 'uri').split('/')[-1])
   

class project_test:
     
    def create_project_test(self):
        p = Projects(name='test', git_url='git://localhost')
        p.save()
        assert_not_equal(None, p.id)
        assert_equal(Projects().get_all().count(), 1)
     

    def get_all_projects_test(self):
        p1 = Projects(name='test', git_url='git://localhost')
        p1.save()

        p2 = Projects(name='test', git_url='git://localhost')
        p2.save()

        assert_true(Projects().get_all().count() >= 2)

    def get_name_test(self):
        p1 = Projects(name='name', git_url='..')
        p1.save()
        pp = Projects().get('name')
        assert_equal(pp.name, 'name')
