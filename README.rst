NFT Meow API
============

This project contains the backend for NFT Meow. NFT data is aggregated using
Apibara.


The code in this repository is deployed at the following address:

https://nftmeow-api.apibara.com/

You can visit the link to interact with the GraphQL API.

Pagination
----------

The GraphQL API follows the `Relay Specification <https://relay.dev/docs/guides/graphql-server-specification/>`_
for pagination.

Example Queries
---------------

**List collections**

.. code:: graphql

    {
      collections {
        edges {
          node {
            name
            address
          }
        }
      }
    }


**List tokens owned by a user**

.. code:: graphql

    {
      tokens(owner: { eq: "0x05ee617dd6946474dd834105c0f986ce8fdd50112851f579cb2e0deed59b876d" }) {
        edges {
          node {
            tokenId
            collection {
              name
            }
            owners
          }
        }
      }
    }


**List tokens in a collection**

.. code:: graphql

    {
      tokens(collection: { eq: "0x0270624780e89ff3ebee0e27409b5577a7916e135f792abcbf9ddc66fbf67b26" }) {
        edges {
          node {
            tokenId
            collection {
              address
              name
            }
            owners
          }
        }
      }
    }


**List most recent mints**

.. code:: graphql

    {
      transfers(first: 10, fromAddress: { eq: "0x0" }) {
        edges {
          node {
            fromAddress
            toAddress
            time
            token {
              tokenId
              collection {
                name
              }
            }
          }
        }
      }
    }


Getting Started
---------------

Start by installing `docker-compose` and using it to run MongoDB and Apibara Server.

- :code:`docker-compose up`

Then install Poetry and the Python dependencies needed by this project.

- :code:`poetry install`

Finally, run the indexer.

- :code:`nftmeow indexer`
