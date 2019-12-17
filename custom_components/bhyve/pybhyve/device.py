
class BHyveDevice(object):

    def __init__(self, name, bhyve, attrs):
        self._name = name
        self._bhyve = bhyve
        self._attrs = attrs

        self._device_id = attrs.get('id', None)

    def __repr__(self):
        # Representation string of object.
        return "<{0}:{1}:{2}>".format(self.__class__.__name__, self.device_type, self._name)

    @property
    def name(self):
        return self._name

    @property
    def device_id(self):
        return self._device_id

    @property
    def device_type(self):
        return self._attrs.get('type', None)

    @property
    def user_id(self):
        return self._attrs.get('user_id', None)

    @property
    def unique_id(self):
        return self._attrs.get('mac_address', None)

    @property
    def is_connected(self):
        return self._attrs.get('is_connected')

    def attribute(self, attr, default=None):
        value = self._attrs.get(attr, None)
        if value is None:
            value = default
        return value

    @property
    def state(self):
        if not self.is_connected:
            return 'unavailable'
        return 'idle'

    @property
    def is_on(self):
        return True

    def turn_on(self):
        pass

    def turn_off(self):
        pass

