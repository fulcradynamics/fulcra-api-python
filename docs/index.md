# `fulcra-api`: A Fulcra API client library for Python

The fulcra-api library is currently compatible with Python 3.9 and up.

## Installation

### Installing in your project

First, install the `fulcra-api` module in your project.

If you're using Poetry, use:
```python
poetry add fulcra-api
```

If you're using pip, use:

```python
pip install fulcra-api
```

### Installing in a Jupyter notebook

In a Python cell in your notebook, use:
```
%pip install fulcra-api
```

*Colaboratory note*: You may see a dependency error while installing pyarrow; this
can be ignored.

## Quick Start

### Logging In

Most Fulcra API requests are authenticated with a token, which must be passed along 
with each request.  The Fulcra API uses Auth0's 
[Device Authorization Flow](https://auth0.com/docs/get-started/authentication-and-authorization-flow/device-authorization-flow)
to authorize the code running and get a token.

This library simplifies this flow for you; to log in, create an instance of the
`FulcraAPI` class and call `authorize` on it:

```python
from fulcra_api.core import FulcraAPI
fulcra = FulcraAPI()
fulcra.authorize()
```

As part of this flow, you'll be asked to visit a webpage to authenticate to Fulcra.
The URL of this page will be included in the output; the library will also attempt
to open a new tab to the URL automatically.

As a user, just click "Confirm" once you've logged in; once this succeeds, close the
tab.

When this succeeds, the call to `authorize()` will return, and the `fulcra` object will
now make calls.  It will take care of refreshing the token and including it with API
calls.

## Making API Calls

Once you've called `authorize` once, any of the calls in the [FulcraAPI class](fulcraapi.md)
will work.  Here's an example that will retrieve the calendars from your data store:

```
calendars = fulcra.calendars()
```

## Examples

You can find some demo notebooks in the [Fulcra demos repository](https://github.com/fulcradynamics/demos).


## Bugs / Feature Requests

Feel free to report any bugs or feature requests using GitHub issues.

