"""
instead of writing one giant checking function, the code makes a small object for each column.
That object remembers the rules for that one column and knows how to check a value against them.
Those objects are called Fields.
"""

from datetime import datetime


# Makes a blueprint for objects
class Field:
    # A special method that runs the moment you make new field
    # * forces you to name your arguments Field(required=False)
    def __init__(self, *, required: bool = True, default=None):
        # the column should be mandatory (defaults to True)
        self.required = required
        # None as a fallback value to use if none is given
        self.default = default
        # Doesn't know its name(column) yet
        self.name: str | None = None

    def __set_name__(self, owner, name):
        # Called automatically by Python when this Field is assigned to an object
        # class attribute, e.g. `email = StringField()` -> self.name = "email".
        # Owner is the class it was attached to
        self.name = name

    # The base `Field` has a method called validate. It belongs to  an object.
    def validate(self, value):
        if value is None:
            # Missing value: fall back to default, or reject if required.
            if self.default is not None:
                return self.default
            if self.required:
                raise ValueError(f"'{self.name}' is required")
            # we got nothing, no fallback, but it's optional
            return None
        return value


class IntField(Field):
    # Inheritance gets the __init__ and __set_name__, all of it
    # Only needs to add what's different -- stricter validate
    def validate(self, value):
        # super() means the "parent class": run the base Field's validate, take whatever it returns and keep going
        value = super().validate(value)
        if value is None:
            return value  # if legit None, then None
        # bool is a subclass of int in Python, so exclude it explicitly. In Python, True and False secretly count as the numbers 1 and 0.
        # isinstance(value, int) means "is this value an integer?"
        # isinstance(True, int) is suprisingly True. So, need to explicitly handle this boolean. If it's a boolean, reject it too.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"'{self.name}' must be an integer")
        return value


class StringField(Field):
    # It accepts a max_length, so it needs its own __init__.
    def __init__(self, *, max_length: int = 255, **kwargs):
        # let the parent's setup (base Field) hanld required and default as usual.
        # keyword arguments scoops up any other options you passed (required, default) and forwards them to the parent
        super().__init__(**kwargs)
        self.max_length = max_length

    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return value
        if not isinstance(value, str):
            # If not text, reject
            raise ValueError(f"'{self.name}' must be a string")
        # Enforces the same length limit the DB column would enforce.
        if len(value) > self.max_length:
            raise ValueError(
                f"'{self.name}' must be at most {self.max_length} characters"
            )
        return value


class BoolField(Field):
    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return value
        if not isinstance(value, bool):
            raise ValueError(f"'{self.name}' must be a boolean")
        return value


class DateTimeField(Field):
    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return value
        if not isinstance(value, datetime):
            raise ValueError(f"'{self.name}' must be a datetime")
        return value
