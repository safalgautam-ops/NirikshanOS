"""Custom ORM base class.

Remember the goal: let you work with database tables using Python classes instead of writing raw SQL everywhere.

A Model subclass declares a table name and a set of Field attributes.
This base class turns those declarations into parameterized SQL -
table/column names come only from the declared Field attributes (a
closed whitelist), and all values are passed to the driver as query
parameters. No feature code should build SQL by string concatenation.

Example:

    class User(Model):
        __table__ = "users"

        email = StringField(max_length=255) #attribute
        password_hash = StringField(max_length=255) #attribute
        created_at = DateTimeField(required=False) #attribute

        #attributes are the fields, each one is set to Field object.

    user = await User.find(1) #fetch the user with id 1
    users = await User.where(email="a@b.com") #fetch all users with email "a@b.com"

    @classmethod and cls. Normally a method works on one object (self = the one specific object).
    A @classmethod instead works on the class itself, and by convention its first parameter is called cls (the class) rather than self.

    class User(Model): is Inheritance, not an object
    user = User(...) is Instantiation, this makes an object

    Think about User.find(5). You're calling find before you have any user object —
    you're asking the class "go find user 5 and make an object for me."
    So find can't take self (there's no object yet); it takes cls (the User class) and
    uses it to know which table to look in. Rule of thumb: methods that create or fetch objects are @classmethod;
    methods that operate on an existing object (like save on a user you already have) use self.

    setattr and getattr. These let you set or read an attribute when the attribute's name is decided at runtime (stored in a variable) rather than typed literally.

    setattr(obj, "email", "a@b.com") is the same as obj.email = "a@b.com".
    getattr(obj, "email") is the same as obj.email.

    You need these because the code loops over column names it doesn't know in advance,
    so it can't type obj.email literally — it has the name in a variable and uses setattr/getattr.
"""

from app.core.db.fields import Field, IntField
from app.core.db.pool import execute, fetchall, fetchone


# Model is the generic base that every table class inherits from.
class Model:
    __table__: str = ""  # Name of the database table(double underscore are justu a naming style signaling it's a private variable)

    id = IntField(
        required=False
    )  # Every table(model) automatically gets an id column (acting as the primary key) for free.
    # It's required=False because when you create a new object, it doesn't have an id yet; the database assigns one when you save it.

    # When you call User(email="anna@x.com"), the __init__ is the setup that runs for that object.
    # the **values scoops up everything you passed by name into a dictionary called values.
    # values = {"email": "anna@x.com"} Notice: you passed only email. You did not pass id, password_hash, or created_at.
    # So values has just the one entry.
    def __init__(self, **values):
        # self.fields() returns the dictionary of all this model's columns
        # fields() is a method whose only job is to scan the class and collect those Field attributes you wrote, gathering them into one tidy dictionary.
        # looping over the dictionary gives its keys -- the column names
        # the column name is different every time (Pass 1: name = "id"; Pass 2: name = "email")
        for name in self.fields():
            # values.get(name) looks up name in the values dictionary, returning the value if present, or None if it's missing.
            # sets the attribute named name on the boject to X equivalent to self.<name> = X, but with the name coming from a variable
            setattr(self, name, values.get(name))

    # helper method to collect all Field attributes from the class hierarchy
    @classmethod
    def fields(cls) -> dict[str, Field]:
        # Walks the class hierarchy (base Model first, then subclass) so a
        # subclass's own Field attributes are collected alongside `id`.
        # "Look through the User class (and its parent Model).
        # For every attribute, check: is this attribute a Field object? If yes, collect it.
        # Return all the Field attributes I found."
        fields: dict[str, Field] = {}
        for klass in reversed(
            cls.__mro__
        ):  # MRO stands for Method Resolution Order, chain of classes from the subclass up through its parents.
            for name, value in vars(
                klass
            ).items():  # vars(klass) returns a dictionary of all attributes of the class, including fields.
                # isinstance(value, Field) checks if the value is a Field object (i.e., it's a column definition).
                # checks the type of the value, from Field class.
                # other attributes -- methods like save, config like __table__ are not collected here.
                if isinstance(value, Field):
                    fields[name] = value
        return fields

        """
        So when you call User.fields(), it returns:
        python{
            "id":            <IntField object>,
            "email":         <StringField object>,
            "password_hash": <StringField object>,
            "created_at":    <DateTimeField object>,
        }
        A dictionary mapping each field name (text) → the Field object you declared. That's all fields() does — it hands back the fields you wrote in the class, collected together.
        """

    # Returns the column names (field names) of this model, in the order they were defined.
    # ["id", "email", "password_hash", "created_at"].
    @classmethod
    def _columns(cls) -> list[str]:
        # The whitelist of column names every query is built from - never
        # taken from user input.
        return list(cls.fields().keys())

    @classmethod
    def _from_row(cls, row: tuple) -> "Model":
        # row is a tuple of values from the database, in the same order as _columns().
        # (1, "anna@x.com", "hashed_pw", None)
        # Zips a raw DB row back into named fields, in the same order they
        # were selected by _columns().
        return cls(
            **dict(zip(cls._columns(), row))
        )  # dict(...) turns those pairs into a dictionary
        # cls(**dict(...)) calls the class constructor with the dictionary of field values.

    """
    Above Result:
    a fully-built User object with named attributes, reconstructed from the anonymous database row.
    This works because _columns() and the SELECT both use the same order —
    that's what keeps each value lined up with the right name.
    """

    # find() -- fetch one row by id
    @classmethod
    async def find(cls, id: int) -> "Model | None":
        columns = ", ".join(
            cls._columns()
        )  # takes the column names list and glue them into one comma-separated string
        # `id` is the only value in the query and it's passed as a parameter,
        # not interpolated - this is what prevents SQL injection here. #_columns and __table__ are safe here.
        query = f"SELECT {columns} FROM {cls.__table__} WHERE id = %s"
        # fetchone() handles acquiring/releasing the connection.
        row = await fetchone(query, (id,))
        # if a row came back, convert it to a Model object and return it; otherwise return None
        return cls._from_row(row) if row else None

    """
    where() -- fetch multiple rows by conditions
    """

    @classmethod
    # fetching multiple rows by conditions (User.where(email="anna@x.com"))
    # **conditions -- scoops the keyword arguments into a dictionary of conditions
    async def where(cls, **conditions) -> list["Model"]:
        # Build the column list and base query string
        columns = ", ".join(cls._columns())
        query = f"SELECT {columns} FROM {cls.__table__}"
        # an empty list to collect query parameters
        params: list = []

        # If there are conditions, build the WHERE clause
        if conditions:
            # gets the whitelist of valid columns
            allowed = cls.fields()
            clauses = []
            # iterates over the conditions dictionary to build the WHERE clause
            for key, value in conditions.items():
                # Reject any column name that isn't a declared Field - this
                # is the whitelist that keeps WHERE clauses injection-safe.
                if key not in allowed:
                    raise ValueError(f"Unknown field '{key}' on {cls.__name__}")
                clauses.append(f"{key} = %s")  # builds a piece of SQL like email = %s
                params.append(value)  # store the actual value separately in params
            query += " WHERE " + " AND ".join(clauses)

        # Values go in as `params`, never spliced into `query`. fetchall()
        # handles acquiring/releasing the connection.
        rows = await fetchall(query, params)
        return [cls._from_row(row) for row in rows]

    """
    all() -- fetch all rows
    User.all() returns every row in the table. It just calls where() with no conditions —
    and you saw above that where with no conditions skips the WHERE clause entirely, producing SELECT ... FROM users (everything).
    So all() cleanly reuses where() rather than duplicating logic.
    """

    @classmethod
    async def all(cls) -> list["Model"]:
        # where() with no conditions -> "SELECT ... FROM table" (no WHERE).
        return await cls.where()

    # insert a new row or update an existing one
    async def save(self) -> None:
        # Every column except the auto-increment primary key.
        columns = [c for c in self._columns() if c != "id"]
        # Collect the values for each column to insert or update
        values = [getattr(self, c) for c in columns]

        # If no id, this is a new row; if id exists, this is an update.
        # User(email=...) has id = None. No id means it was never saved, so it's new --> INSERT
        if self.id is None:
            # Make an INSERT query with placeholders for each column value: "%s, %s, %s"
            placeholders = ", ".join(["%s"] * len(columns))
            #  build SQL like INSERT INTO users (email, password_hash, created_at) VALUES (%s, %s, %s)
            query = (
                f"INSERT INTO {self.__table__} ({', '.join(columns)}) "
                f"VALUES ({placeholders})"
            )
            # execute() commits and returns lastrowid - pick up the
            # auto-generated primary key for this object.
            self.id = await execute(query, values)
        else:
            # Has an id -> existing row, build an UPDATE ... WHERE id.
            # build email = %s, password_hash = %s, created_at = %s (each column set to a placeholder).
            assignments = ", ".join(f"{c} = %s" for c in columns)
            # SQL like UPDATE users SET email = %s, ... WHERE id = %s. The WHERE id = %s ensures only this one row is changed.
            query = f"UPDATE {self.__table__} SET {assignments} WHERE id = %s"
            # execute() handles acquiring the connection and committing.
            # The values + [self.id] are the column values and the id for the WHERE clause.
            await execute(query, values + [self.id])

    async def delete(self) -> None:
        if self.id is None:
            return
        # execute() handles acquiring the connection and committing.
        await execute(f"DELETE FROM {self.__table__} WHERE id = %s", (self.id,))

    # turn an object back into a plain dictionary for JSON serialization.
    def to_dict(self) -> dict:
        # Handy for passing a model straight into render_template() or JSON.
        # For our user it produces {"id": 1, "email": "anna@x.com", "password_hash": "...", "created_at": None}.
        return {name: getattr(self, name) for name in self.fields()}
