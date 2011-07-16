# http://stackoverflow.com/questions/1896918/running-unittest-with-typical-test-directory-structure

import unittest
import test.all_tests
testSuite = test.all_tests.create_test_suite()
text_runner = unittest.TextTestRunner().run(testSuite)

