# Copyright 2013 10gen, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test Motor, an asynchronous driver for MongoDB and Tornado."""

import pymongo
from pymongo.errors import ConfigurationError
from pymongo.read_preferences import ReadPreference
from tornado.testing import gen_test

import motor
from test import host, port, assert_raises, MotorTest


class MotorTestBasic(MotorTest):
    def test_repr(self):
        self.assertTrue(repr(self.cx).startswith('MotorClient'))
        db = self.cx.pymongo_test
        self.assertTrue(repr(db).startswith('MotorDatabase'))
        coll = db.test_collection
        self.assertTrue(repr(coll).startswith('MotorCollection'))
        cursor = coll.find()
        self.assertTrue(repr(cursor).startswith('MotorCursor'))

    @gen_test
    def test_write_concern(self):
        cx = motor.MotorClient(host, port, io_loop=self.io_loop)

        # An implementation quirk of Motor, can't access properties until
        # connected
        self.assertRaises(
            pymongo.errors.InvalidOperation, getattr, cx, 'write_concern')

        yield cx.open()

        # Default empty dict means "w=1"
        self.assertEqual({}, cx.write_concern)
        cx.close()

        for gle_options in [
            {},
            {'w': 0},
            {'w': 1},
            {'wtimeout': 1000},
            {'j': True},
        ]:
            cx = yield self.motor_client(host, port, **gle_options)
            expected_wc = gle_options.copy()
            self.assertEqual(expected_wc, cx.write_concern)

            db = cx.pymongo_test
            self.assertEqual(expected_wc, db.write_concern)

            collection = db.test_collection
            self.assertEqual(expected_wc, collection.write_concern)

            if gle_options.get('w') == 0:
                yield collection.insert({'_id': 0})  # No error
            else:
                with assert_raises(pymongo.errors.DuplicateKeyError):
                    yield collection.insert({'_id': 0})

            # No error
            yield collection.insert({'_id': 0}, w=0)
            cx.close()

        collection = cx.pymongo_test.test_collection
        collection.write_concern['w'] = 2

        # No error
        yield collection.insert({'_id': 0}, w=0)

        cxw2 = yield self.motor_client(w=2)
        yield cxw2.pymongo_test.test_collection.insert({'_id': 0}, w=0)

        # Test write concerns passed to MotorClient, set on collection, or
        # passed to insert.
        if self.is_replica_set:
            with assert_raises(pymongo.errors.DuplicateKeyError):
                yield cxw2.pymongo_test.test_collection.insert({'_id': 0})

            with assert_raises(pymongo.errors.DuplicateKeyError):
                yield collection.insert({'_id': 0})

            with assert_raises(pymongo.errors.DuplicateKeyError):
                yield cx.pymongo_test.test_collection.insert({'_id': 0}, w=2)
        else:
            # w > 1 and no replica set
            with assert_raises(pymongo.errors.OperationFailure):
                yield cxw2.pymongo_test.test_collection.insert({'_id': 0})

            with assert_raises(pymongo.errors.OperationFailure):
                yield collection.insert({'_id': 0})

            with assert_raises(pymongo.errors.OperationFailure):
                yield cx.pymongo_test.test_collection.insert({'_id': 0}, w=2)

        # Important that the last operation on each MotorClient was
        # acknowledged, so lingering messages aren't delivered in the middle of
        # the next test. Also, a quirk of tornado.testing.AsyncTestCase:  we
        # must relinquish all file descriptors before its tearDown calls
        # self.io_loop.close(all_fds=True).
        cx.close()
        cxw2.close()

    @gen_test
    def test_read_preference(self):
        cx = motor.MotorClient(host, port, io_loop=self.io_loop)

        # An implementation quirk of Motor, can't access properties until
        # connected
        self.assertRaises(
            pymongo.errors.InvalidOperation, getattr, cx, 'read_preference')

        # Check the default
        yield cx.open()
        self.assertEqual(ReadPreference.PRIMARY, cx.read_preference)
        cx.close()

        # We can set mode, tags, and latency, both with open() and open_sync()
        cx.close()
        cx = yield self.motor_client(
            read_preference=ReadPreference.SECONDARY,
            tag_sets=[{'foo': 'bar'}],
            secondary_acceptable_latency_ms=42)

        self.assertEqual(ReadPreference.SECONDARY, cx.read_preference)
        self.assertEqual([{'foo': 'bar'}], cx.tag_sets)
        self.assertEqual(42, cx.secondary_acceptable_latency_ms)

        cx.close()
        cx = yield self.motor_client(
            read_preference=ReadPreference.SECONDARY,
            tag_sets=[{'foo': 'bar'}],
            secondary_acceptable_latency_ms=42)

        self.assertEqual(ReadPreference.SECONDARY, cx.read_preference)
        self.assertEqual([{'foo': 'bar'}], cx.tag_sets)
        self.assertEqual(42, cx.secondary_acceptable_latency_ms)

        # Make a MotorCursor and get its PyMongo Cursor
        cursor = cx.pymongo_test.test_collection.find(
            io_loop=self.io_loop,
            read_preference=ReadPreference.NEAREST,
            tag_sets=[{'yay': 'jesse'}],
            secondary_acceptable_latency_ms=17).delegate

        self.assertEqual(
            ReadPreference.NEAREST, cursor._Cursor__read_preference)

        self.assertEqual([{'yay': 'jesse'}], cursor._Cursor__tag_sets)
        self.assertEqual(17, cursor._Cursor__secondary_acceptable_latency_ms)
        cx.close()

    @gen_test
    def test_safe(self):
        # Motor doesn't support 'safe'
        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port, io_loop=self.io_loop, safe=True)

        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port, io_loop=self.io_loop, safe=False)

        collection = self.cx.pymongo_test.test_collection
        self.assertRaises(
            ConfigurationError, collection.insert, {}, safe=False)

        self.assertRaises(
            ConfigurationError, collection.insert, {}, safe=True)

    @gen_test
    def test_slave_okay(self):
        # Motor doesn't support 'slave_okay'
        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port,
            io_loop=self.io_loop, slave_okay=True)

        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port,
            io_loop=self.io_loop, slave_okay=False)

        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port,
            io_loop=self.io_loop, slaveok=True)

        self.assertRaises(
            ConfigurationError,
            motor.MotorClient, host, port,
            io_loop=self.io_loop, slaveok=False)

        collection = self.cx.pymongo_test.test_collection

        self.assertRaises(
            ConfigurationError,
            collection.find_one, slave_okay=True)

        self.assertRaises(
            ConfigurationError,
            collection.find_one, slaveok=True)

        self.cx.close()
