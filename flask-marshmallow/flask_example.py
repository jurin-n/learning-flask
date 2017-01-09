# -*- coding: utf-8 -*-

import datetime

from flask import Flask, jsonify, request, g
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import create_engine
from sqlalchemy.orm.session import Session, sessionmaker
from marshmallow import Schema, fields, ValidationError, pre_load

app = Flask(__name__)
engine = create_engine('sqlite:////tmp/quotes.db', echo=False)

##### MODELS #####
Base = declarative_base()

class Author(Base):
    __tablename__ = 'author'
    id = Column(Integer, primary_key=True)
    first = Column(String(80))
    last = Column(String(80))

class Quote(Base):
    __tablename__ = 'quote'
    id = Column(Integer, primary_key=True)
    content = Column(String, nullable=False)
    author_id = Column(Integer, ForeignKey("author.id"))
    author = relationship("Author",
                        backref=backref("quotes", lazy="dynamic"))
    posted_at = Column(DateTime)

##### SCHEMAS #####

class AuthorSchema(Schema):
    id = fields.Int(dump_only=True)
    first = fields.Str()
    last = fields.Str()
    formatted_name = fields.Method("format_name", dump_only=True)

    def format_name(self, author):
        return "{}, {}".format(author.last, author.first)


# Custom validator
def must_not_be_blank(data):
    if not data:
        raise ValidationError('Data not provided.')

class QuoteSchema(Schema):
    id = fields.Int(dump_only=True)
    author = fields.Nested(AuthorSchema, validate=must_not_be_blank)
    content = fields.Str(required=True, validate=must_not_be_blank)
    posted_at = fields.DateTime(dump_only=True)

    # Allow client to pass author's full name in request body
    # e.g. {"author': 'Tim Peters"} rather than {"first": "Tim", "last": "Peters"}
    @pre_load
    def process_author(self, data):
        author_name = data.get('author')
        if author_name:
            first, last = author_name.split(' ')
            author_dict = dict(first=first, last=last)
        else:
            author_dict = {}
        data['author'] = author_dict
        return data

author_schema = AuthorSchema()
authors_schema = AuthorSchema(many=True)
quote_schema = QuoteSchema()
quotes_schema = QuoteSchema(many=True, only=('id', 'content'))

##### API #####
@app.before_request
def before_request():
    print('[DEBUG]before request')
    Session = sessionmaker(bind=engine, autocommit=True)
    g.db_session = Session()

@app.teardown_request
def teardown_request(exception):
    print('[DEBUG]teardown requesst')

@app.route('/authors')
def get_authors():
    authors = Author.query.all()
    # Serialize the queryset
    result = authors_schema.dump(authors)
    return jsonify({'authors': result.data})

@app.route("/authors/<int:pk>")
def get_author(pk):
    try:
        author = Author.query.get(pk)
    except IntegrityError:
        return jsonify({"message": "Author could not be found."}), 400
    author_result = author_schema.dump(author)
    quotes_result = quotes_schema.dump(author.quotes.all())
    return jsonify({'author': author_result.data, 'quotes': quotes_result.data})

@app.route('/quotes/', methods=['GET'])
def get_quotes():
    quotes = g.db_session.query(Quote).all()
    result = quotes_schema.dump(quotes)
    return jsonify({"quotes": result.data})

@app.route("/quotes/<int:pk>")
def get_quote(pk):
    try:
        quote = Quote.query.get(pk)
    except IntegrityError:
        return jsonify({"message": "Quote could not be found."}), 400
    result = quote_schema.dump(quote)
    return jsonify({"quote": result.data})

@app.route("/quotes/", methods=["POST"])
def new_quote():
    json_data = request.get_json()
    if not json_data:
        return jsonify({'message': 'No input data provided'}), 400
    # Validate and deserialize input
    data, errors = quote_schema.load(json_data)
    if errors:
        return jsonify(errors), 422
    first, last = data['author']['first'], data['author']['last']
    author = Author.query.filter_by(first=first, last=last).first()
    if author is None:
        # Create a new author
        author = Author(first=first, last=last)
        db.session.add(author)
    # Create new quote
    quote = Quote(
        content=data['content'],
        author=author,
        posted_at=datetime.datetime.utcnow()
    )
    db.session.add(quote)
    db.session.commit()
    result = quote_schema.dump(Quote.query.get(quote.id))
    return jsonify({"message": "Created new quote.",
                    "quote": result.data})

if __name__ == '__main__':
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.run(debug=True, port=5000)
