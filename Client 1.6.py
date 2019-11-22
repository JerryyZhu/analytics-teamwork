import sqlite3
import json
import ast
import pandas as pd
from flask import Flask, request, jsonify
from flask_restplus import Resource, Api, fields, inputs, abort
from data_management import metadata_manager
from Create_db import create_connection
#from itsdangerous import JSONWebSignatureSerializer as Serializer
from auth import *


app = Flask(__name__)
api = Api(app, version='1.5', default="Board Game Geek",
          title="Board Game Geek Dataset", description="...",
          authorizations={
              'API-KEY': {
                  'type': 'apiKey',
                  'in': 'header',
                  'name': 'AUTH-TOKEN'
              }
          },
          security='API-KEY')

mm = metadata_manager.MetaDataManager()


# Get row entries of dataframe, starting from a row index num_rows and extending for
# num_rows. Output can be in dict. All numpy NaN and NA values are converted to
# null / None. A list of dataframe column names can be provided to interpret each element under
# that column as a list.


def get_dict_entries(df, start_pos=None, num_rows=None, keyval_list=[]):
    if start_pos == None:
        start_pos = 0
    end_pos = len(df.index) if (num_rows == None) else min(
        start_pos + num_rows, len(df.index))
    selected = df.iloc[start_pos: end_pos].replace({pd.np.nan: None})
    # all remaining NaN values to be converted to None (client is pure Python)
    # all specified keys to interpret their vals as Python lists (if not None)
    row_entries = selected.to_dict(orient='records')
    if len(keyval_list) > 0:
        for i in range(len(row_entries)):  # row
            for key in keyval_list:  # specified column (key)
                if row_entries[i][key] != None:  # null or list
                    row_entries[i][key] = ast.literal_eval(row_entries[i][key])
    return row_entries


review_model = api.model('Review', {
    'Game_ID': fields.Integer,
    'User': fields.String,
    'Rating': fields.Float,
    'Comment': fields.String,
})

detail_model = api.model('Detail', {
    'Game_ID': fields.Integer,
    'Name': fields.String,
    'Publisher': fields.List(fields.String),
    'Category': fields.List(fields.String),
    'Min_players': fields.Integer,
    'Max_players': fields.Integer,
    'Min_age': fields.Integer,
    'Min_playtime': fields.Integer,
    'Description': fields.String,
    'Expansion': fields.List(fields.String),
    'Mechanic': fields.List(fields.String),
    'Thumbnail': fields.Url,
    'Year_Published': fields.Integer
})

game_model = api.model('Game', {
    'Game_ID': fields.Integer,
    'Name': fields.String,
    'Year': fields.Integer,
    'Rank': fields.Integer,
    'Average': fields.Float,
    'Bayes_Average': fields.Float,
    'Users_Rated': fields.Integer,
    'URL': fields.Url,
    'Thumbnail': fields.Url
})


###GET API STATS###
@api.route('/api_usage')
class Api_Usage(Resource):
    @api.response(200, 'Successful')
    @api.doc(description='Get Api Usage Stats')
    def get(self):
        api_usage = mm.metadata
        mm.increment('/api_usage')
        return api_usage, 200



@api.route('/details')
class Board_Games_Details_List(Resource):

    ###GET GAMES DETAILS###
    @api.response(200, 'Successful')
    @api.doc(description='Get all board games details')
    def get(self):
        mm.increment('/details')
        conn = create_connection('Database')
        # Chunk this to be loaded onto multiple pages
        df = pd.read_sql_query("SELECT * FROM Details;", conn)
        return get_dict_entries(df)

    ###POST GAME DETAILS###
    @api.response(201, 'Board Game Details Added Successfully')
    @api.response(400, 'Validation Error')
    @api.doc(description="Add new board game details")
    @api.expect(detail_model, validate=True)
    def post(self):
        details = request.json
        for key in details:
            if key not in detail_model.keys():
                return {"message": "Property {} is invalid".format(key)}, 400

        conn = create_connection('Database')
        df = pd.read_sql_query(
            "SELECT Name FROM Details WHERE Game_ID = {};".format(details['Game_ID']), conn)
        if len(df) > 0:
            api.abort(400, "Game {} already exists".format(details['Game_ID']))
        c = conn.cursor()
        c.execute("INSERT INTO Details(Game_ID, Name, Publisher, Category, Min_players, Max_players, Min_age, Min_playtime, Description, Expansion, Mechanic, Thumbnail, Year_Published) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (details['Game_ID'],
                   details['Name'],
                   str(details['Publisher']),
                   str(details['Category']),
                   details['Min_players'],
                   details['Max_players'],
                   details['Min_age'],
                   details['Min_playtime'],
                   details['Description'],
                   str(details['Expansion']),
                   str(details['Mechanic']),
                   details['Thumbnail'],
                   details['Year_Published']))
        conn.commit()
        mm.increment('/board_games_details/POST {}'.format(details['Game_ID']))
        return {"message": "Game {} is created with ID {}".format(details['Name'], details['Game_ID'])}, 201


    ###UPDATE GAME DETAILS###
    @api.response(404, 'Game not found')
    @api.response(400, 'Validation Error')
    @api.response(200, 'Successful')
    @api.expect(detail_model)
    @api.doc(description="Update a game details by its ID")
    def put(self):
        details = request.json
        conn = create_connection('Database')
        c = conn.cursor()
        df = pd.read_sql_query(
            "SELECT Detail_ID FROM Details WHERE Game_ID = {}".format(details['Game_ID']), conn)
        if len(df) == 0:
            api.abort(404, "Game {} doesn't exist".format(details['Game_ID']))
        index = df.loc[0][0]

        for key in details:
            if key not in detail_model.keys():
                return {"message": "Property {} is invalid".format(key)}, 400

        c.execute('UPDATE Details SET Name=?, Publisher=?, Category=?, Min_players=?, Max_players=?, Min_age=?, Min_playtime=?, Description=?, Expansion=?, Mechanic=?, Thumbnail=?, Year_Published=? WHERE Detail_ID=?;', (
            str(details['Name']),
            str(details['Publisher']),
            str(details['Category']),
            details['Min_players'],
            details['Max_players'],
            details['Min_age'],
            details['Min_playtime'],
            str(details['Description']),
            str(details['Expansion']),
            str(details['Mechanic']),
            str(details['Thumbnail']),
            details['Year_Published'],
            int(index)))

        conn.commit()
        mm.increment('/board_games_details/PUT {}'.format(details['Game_ID']))

        return {"message": "Game {} has been successfully updated".format(details['Game_ID'])}, 200

    


@api.route('/details/<int:id>')
@api.param('id', 'Game ID')
class Board_Games(Resource):

    ###GET GAME DETAILS BY ID###
    @api.response(404, 'Game not found')
    @api.response(200, 'Successful')
    @api.doc(description="Get a game details by its ID")
    def get(self, id):
        conn = create_connection('Database')
        df = pd.read_sql_query(
            "SELECT * FROM Details WHERE Game_ID = {};".format(id), conn)
        if len(df) == 0:
            api.abort(404, "Game {} doesn't exist".format(id))
        details = df.loc[0].to_json()
        details = json.loads(details)

        mm.increment('/board_games_details/{}'.format(id))
        return details, 200



    
@api.route('/reviews')
class addReviews(Resource):

    ###POST REVIEW###
    @api.response(201, 'Review Added Successfully')
    @api.response(400, 'Validation Error')
    @api.doc(description="Add a new review")
    @api.expect(review_model, validate=True)
    @requires_auth
    def post(self):
        review = request.json

        for key in review:
            if key not in review_model.keys():
                return {"message": "Property {} is invalid".format(key)}, 400

        conn = create_connection('Database')
        df = pd.read_sql_query(
            "SELECT Name FROM Details WHERE Game_ID = {};".format(review['Game_ID']), conn)
        if len(df) == 0:
            api.abort(404, "Game {} doesn't exist".format(review['Game_ID']))
        Name = df.loc[0][0]
        c = conn.cursor()
        c.execute("INSERT INTO Reviews(User, Rating, Game_ID, Comment, Name) VALUES(?,?,?,?,?)",
                  (review['User'], review['Rating'], review['Game_ID'], review['Comment'], Name))
        last_row = c.lastrowid
        conn.commit()
        mm.increment('/reviews/POST {}'.format(id))
        return {"message": "Review for game '{}' has been added with ID {}".format(Name, last_row)}, 201


@api.route('/reviews/<int:id>')
@api.param('id', 'Game ID')
class Reviews(Resource):
    ###GET REVIEWS FOR A GAME###
    @api.response(404, 'Review not found')
    @api.response(200, 'Successful')
    @api.doc(description="Get all reviews for a specific game")
    def get(self, id):
        conn = create_connection('Database')
        df = pd.read_sql_query(
            "SELECT Name FROM Details WHERE Game_ID = {};".format(id), conn)
        if len(df) == 0:
            api.abort(404, "Game {} doesn't exist".format(id))
        df = pd.read_sql_query(
            "SELECT * FROM Reviews WHERE Game_ID = {};".format(id), conn)
        if len(df) == 0:
            api.abort(404, "There are no reviews for {} doesn't exist".format(id))

        mm.increment('/review/{}'.format(id))
        return get_dict_entries(df), 200


    

@api.route('/auth')
class Token(Resource):
    @api.response(200, 'Successful')
    @api.doc(description="Get a token to access the end points")
    def get(self):
        return {'token': auth.generate_token().decode()}, 200


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000, debug=True)