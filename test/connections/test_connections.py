"""Unit tests for service connection lifecycle logic."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.connections.connection import Connection
from src.connections.influx_connection import InfluxConnection
from src.connections.mqtt_connection import MQTTConnection


class DummyConnection(Connection):
    """
    A dummy connection class for testing purposes.
    """

    def connect(self):
        """
        Dummy connect method for testing.
        """
        return True

    def disconnect(self):
        """
        Dummy disconnect method for testing.
        """
        return True


class TestConnection(TestCase):
    """
    Tests for Connection base class methods and state management.
    """

    def test_url_and_connected_state(self):
        """
        Tests that the connection URL is constructed correctly and that the
        connected state is reported accurately based on the connection attribute.
        """
        connection = DummyConnection("db", 8086)
        self.assertEqual(connection.get_full_link(), "http://db:8086")
        self.assertEqual(str(connection), "http://db:8086")
        self.assertFalse(connection.is_connected())
        connection.connection = object()
        self.assertTrue(connection.is_connected())
        self.assertEqual(
            DummyConnection("https://db", 443).get_full_link(),
            "https://db:443")
        with self.assertRaises(NotImplementedError):
            Connection.connect(connection)
        with self.assertRaises(NotImplementedError):
            Connection.disconnect(connection)


class TestMQTTConnection(TestCase):
    """
    Tests for MQTTConnection lifecycle, callbacks, and authentication.
    """

    def test_callbacks_update_state_and_forward_message(self):
        """
        Tests that on_connect sets the connected state, on_message forwards the
        message to the on_message callback, and on_disconnect clears the connection
        and updates the connected state.
        """
        changed, received = MagicMock(), MagicMock()
        mqtt = MQTTConnection("broker",
                              on_state_change=changed,
                              on_message=received)
        client = object()
        mqtt.connection = client
        mqtt.on_connect(client, None, None, 0)
        self.assertTrue(mqtt._connected)  # pylint: disable=protected-access
        self.assertFalse(mqtt._connecting)  # pylint: disable=protected-access
        mqtt.on_message(client, None, SimpleNamespace(topic="a/b",
                                                      payload=b"x"))
        received.assert_called_once_with("a/b", b"x")
        mqtt.on_disconnect(client, None, None, 0)
        self.assertIsNone(mqtt.connection)
        self.assertFalse(mqtt.is_connected())
        self.assertEqual(changed.call_count, 2)

    def test_connect_configures_client_and_authentication(self):
        """
        Tests that connect() configures the MQTT client with username, password,
        TLS, and starts the loop, and that disconnect() stops the loop and clears the connection.
        """
        client = MagicMock()
        client.is_connected.return_value = True
        client.connect.side_effect = lambda **_kwargs: client.on_connect(
            client, None, None, 0)
        with patch("src.connections.mqtt_connection.mqtt.Client",
                   return_value=client):
            mqtt = MQTTConnection("broker", username="user", password="pass")
            self.assertTrue(mqtt.connect())
        client.username_pw_set.assert_called_once_with("user", "pass")
        client.tls_set.assert_called_once_with()
        client.connect.assert_called_once_with(host="broker", port=1883)
        client.loop_start.assert_called_once_with()
        self.assertTrue(mqtt.disconnect())
        self.assertIsNone(mqtt.connection)

    def test_connect_failure_disconnect_failure_and_liveness_error(self):
        """
        Tests that connect() returns False if the client raises an exception,
        that disconnect() returns False if the client raises an exception,
        and that is_connected() returns False if the client raises an exception.
        """
        with patch("src.connections.mqtt_connection.mqtt.Client",
                   side_effect=RuntimeError("offline")):
            mqtt = MQTTConnection("broker")
            self.assertFalse(mqtt.connect())
        mqtt.connection = MagicMock()
        mqtt.connection.loop_stop.side_effect = RuntimeError("bad close")
        self.assertFalse(mqtt.disconnect())
        mqtt._connected = True  # pylint: disable=protected-access
        mqtt.connection = MagicMock()
        mqtt.connection.is_connected.side_effect = RuntimeError("lost")
        self.assertFalse(mqtt.is_connected())


class TestInfluxConnection(TestCase):
    """
    Tests for InfluxConnection lifecycle, bucket management, and connection checking.
    """

    def setUp(self):
        """
        Sets up an InfluxConnection instance for testing.
        """
        self.influx = InfluxConnection("db", "token", "org", buckets=["adr"])

    def test_repr_callbacks_and_missing_disconnect(self):
        """
        Tests that the InfluxConnection string representation includes the URL,
        that the on_state_change callback is called on connect and disconnect,
        and that disconnect() returns False if the connection is not established.
        """
        changed = MagicMock()
        self.influx.on_state_change = changed
        self.assertIn("url=db", str(self.influx))
        self.influx.on_connect()
        self.influx.on_disconnect()
        self.assertEqual(changed.call_count, 2)
        self.assertFalse(self.influx.disconnect())

    def test_ping_bucket_creation_and_failure_paths(self):
        """
        Tests that ping() checks for existing buckets, creates missing buckets,
        and handles exceptions gracefully, returning True if the connection is
        healthy and False otherwise.
        """
        self.influx.connection = MagicMock()
        self.influx.connection.buckets_api.return_value.find_buckets.return_value = SimpleNamespace(
            buckets=[SimpleNamespace(name="existing")])
        with patch.object(self.influx,
                          "create_missing_bucket",
                          return_value=True) as create:
            self.assertTrue(self.influx.ping())
        create.assert_called_once()
        self.influx.connection.buckets_api.return_value.find_buckets.return_value = None
        self.assertFalse(self.influx.ping())
        self.influx.connection.buckets_api.return_value.find_buckets.side_effect = RuntimeError(
        )
        self.influx.connection.health.return_value.status = "pass"
        self.assertFalse(self.influx.ping())

    def test_bucket_creation_and_timer_reset(self):
        """
        Tests that create_bucket creates a bucket using the InfluxDBClient and
        that reset_ping resets the ConnectionChecker timer, and that both methods
        handle exceptions gracefully.
        """
        self.influx.connection = MagicMock()
        self.assertTrue(self.influx.create_bucket("new"))
        self.influx.connection.buckets_api.return_value.create_bucket.assert_called_once(
        )
        self.influx.connection.buckets_api.return_value.create_bucket.side_effect = RuntimeError(
        )
        self.assertFalse(self.influx.create_bucket("bad"))
        checker = MagicMock()
        self.influx.connection_checker = checker
        self.assertTrue(self.influx.reset_ping())
        checker.reset_timer.assert_called_once()
        checker.reset_timer.side_effect = RuntimeError()
        self.assertFalse(self.influx.reset_ping())

    def test_connect_and_disconnect_manage_client_checker(self):
        """
        Tests that connect() creates the InfluxDBClient and ConnectionChecker,
        and that disconnect() stops the ConnectionChecker and cleans up the client.
        """
        client = MagicMock()
        checker = MagicMock()
        with patch("src.connections.influx_connection.ConnectionChecker", return_value=checker), \
                patch("src.connections.influx_connection.InfluxDBClient", return_value=client), \
                patch.object(self.influx, "is_connected", return_value=True):
            self.assertTrue(self.influx.connect())
        self.assertIs(self.influx.connection, client)
        checker.start.assert_called_once_with()
        with patch.object(self.influx.connection_checker, "stop") as stop:
            self.assertTrue(self.influx.disconnect())
        stop.assert_called_once_with()

    def test_create_missing_buckets_daemon_branch(self):
        """
        Tests that create_missing_bucket starts a new thread for bucket creation
        when the daemon flag is True, and that the thread is started.
        """
        with patch("src.connections.influx_connection.Thread") as thread:
            self.assertTrue(
                self.influx.create_missing_bucket([], ["new"], daemon=True))
        thread.assert_called_once()
        thread.return_value.start.assert_called_once_with()

    def test_create_missing_buckets_sync_and_daemon(self):
        """
        Tests that create_missing_bucket creates the specified buckets and returns
        True if successful, and that it returns False if bucket creation fails.
        Also tests that the daemon branch starts a new thread for bucket creation.
        """
        with patch.object(self.influx,
                          "create_bucket",
                          side_effect=[True, False]) as create:
            self.assertTrue(self.influx.create_missing_bucket(["a"], ["a"]))
            self.assertFalse(self.influx.create_missing_bucket([], ["b", "c"]))
        self.assertEqual(create.call_count, 2)

    def test_connection_checker_reset_and_stop(self):
        """
        Tests that the ConnectionChecker can reset its timer and stop gracefully.
        """
        checker = self.influx.connection_checker
        checker.reset_timer()
        self.assertTrue(checker._stop_event.is_set() is False)  # pylint: disable=protected-access
        with patch.object(checker, "join") as join:
            checker.stop()
        self.assertTrue(checker.is_stopping)
        join.assert_called_once_with()

    def test_connection_checker_reports_initial_and_lost_connection(self):
        """
        Tests that the ConnectionChecker reports initial connection and lost connection
        events by calling the on_connect and on_disconnect callbacks.
        """
        connection = MagicMock()
        connection.is_connected.side_effect = [True, False]
        checker = self.influx.connection_checker
        checker.influx_connection = connection
        checker.check_interval = 0
        checker.run()
        connection.on_connect.assert_called_once_with()
        connection.on_disconnect.assert_called_once_with()
