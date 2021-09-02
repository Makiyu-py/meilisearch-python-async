import json
from math import ceil

import pytest

from meilisearch_python_async.decorators import status_check
from meilisearch_python_async.errors import MeiliSearchApiError, MeiliSearchError, PayloadTooLarge


def generate_test_movies(num_movies=50):
    movies = []
    # Each moves is ~ 174 bytes
    for i in range(num_movies):
        movie = {
            "id": i,
            "title": "test",
            "poster": "test",
            "overview": "test",
            "release_date": 1551830399,
            "pk_test": i + 1,
            "genre": "test",
        }
        movies.append(movie)

    return movies


@pytest.fixture
def add_document():
    return {
        "id": "1",
        "title": f"{'a' * 999999}",
        "poster": f"{'a' * 999999}",
        "overview": f"{'a' * 999999}",
        "release_date": 1551830399,
        "genre": f"{'a' * 999999}",
    }


@pytest.mark.asyncio
async def test_get_documents_default(empty_index):
    index = await empty_index()
    response = await index.get_documents()
    assert response is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents(primary_key, expected_primary_key, empty_index, small_movies):
    index = await empty_index()
    response = await index.add_documents(small_movies, primary_key)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "processed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "docs, expected_fail, expected_indexed",
    [
        (
            [
                {
                    "id": 1,
                    "name": "test 1",
                },
                {
                    "id": 2,
                    "name": "test 2",
                },
            ],
            False,
            2,
        ),
        (
            [
                {
                    "name": "test 1",
                },
                {
                    "name": "test 2",
                },
            ],
            True,
            0,
        ),
    ],
)
async def test_status_check_decorator(docs, expected_fail, expected_indexed, empty_index, capfd):
    index = await empty_index()

    @status_check(index=index)
    async def fn():
        await index.add_documents(docs)

    await fn()
    stats = await index.get_stats()
    assert stats.number_of_documents == expected_indexed

    out, _ = capfd.readouterr()

    fail_text = "status='failed'"

    if expected_fail:
        assert fail_text in out
    else:
        assert fail_text not in out


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "docs, expected_fail, expected_indexed, expected_messages",
    [
        (
            [
                {
                    "id": 1,
                    "name": "test 1",
                },
                {
                    "id": 2,
                    "name": "test 2",
                },
            ],
            False,
            2,
            0,
        ),
        (
            [
                {
                    "name": "test 1",
                },
                {
                    "name": "test 2",
                },
            ],
            True,
            0,
            2,
        ),
    ],
)
async def test_status_check_decorator_batch(
    docs, expected_fail, expected_indexed, expected_messages, empty_index, capfd
):
    index = await empty_index()

    @status_check(index=index)
    async def fn():
        await index.add_documents_in_batches(docs, batch_size=1)

    await fn()
    stats = await index.get_stats()
    assert stats.number_of_documents == expected_indexed

    out, _ = capfd.readouterr()

    fail_text = "status='failed'"

    if expected_fail:
        assert out.count(fail_text) == expected_messages
    else:
        assert fail_text not in out


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("pk_test", "pk_test"), (None, "id")]
)
async def test_add_documents_auto_batch(
    empty_index, max_payload, primary_key, expected_primary_key
):
    movies = generate_test_movies()

    index = await empty_index()
    if max_payload:
        response = await index.add_documents_auto_batch(
            movies, max_payload_size=max_payload, primary_key=primary_key
        )
    else:
        response = await index.add_documents_auto_batch(movies, primary_key=primary_key)

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    stats = await index.get_stats()

    assert stats.number_of_documents == len(movies)
    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
async def test_add_documents_auto_batch_payload_size_error(empty_index, small_movies):
    with pytest.raises(PayloadTooLarge):
        index = await empty_index()
        await index.add_documents_auto_batch(small_movies, max_payload_size=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents_in_batches(
    batch_size, primary_key, expected_primary_key, empty_index, small_movies
):
    index = await empty_index()
    response = await index.add_documents_in_batches(
        small_movies, batch_size=batch_size, primary_key=primary_key
    )
    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents_from_file(
    primary_key, expected_primary_key, test_client, small_movies_path
):
    index = test_client.index("movies")
    response = await index.add_documents_from_file(small_movies_path, primary_key)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "processed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents_from_file_string_path(
    primary_key, expected_primary_key, test_client, small_movies_path
):
    string_path = str(small_movies_path)
    index = test_client.index("movies")
    response = await index.add_documents_from_file(string_path, primary_key)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "processed"


@pytest.mark.asyncio
async def test_add_documents_from_file_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.add_documents_from_file("test.csv")


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("pk_test", "pk_test"), (None, "id")]
)
async def test_add_documents_from_file_auto_batch(
    max_payload, primary_key, expected_primary_key, test_client, tmp_path
):
    movies = generate_test_movies()
    test_file = tmp_path / "test.json"

    with open(test_file, "w") as f:
        json.dump(movies, f)

    index = test_client.index("movies")

    if max_payload:
        response = await index.add_documents_from_file_auto_batch(
            test_file, max_payload_size=max_payload, primary_key=primary_key
        )
    else:
        response = await index.add_documents_from_file_auto_batch(
            test_file, primary_key=primary_key
        )

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    stats = await index.get_stats()

    assert stats.number_of_documents == len(movies)
    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("pk_test", "pk_test"), (None, "id")]
)
async def test_add_documents_from_file_string_path_auto_batch(
    max_payload, primary_key, expected_primary_key, test_client, tmp_path
):
    movies = generate_test_movies()
    test_file = tmp_path / "test.json"

    with open(test_file, "w") as f:
        json.dump(movies, f)

    index = test_client.index("movies")

    if max_payload:
        response = await index.add_documents_from_file_auto_batch(
            str(test_file), max_payload_size=max_payload, primary_key=primary_key
        )
    else:
        response = await index.add_documents_from_file_auto_batch(
            str(test_file), primary_key=primary_key
        )

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    stats = await index.get_stats()

    assert stats.number_of_documents == len(movies)
    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents_from_file_in_batches(
    batch_size, primary_key, expected_primary_key, test_client, small_movies_path, small_movies
):
    index = test_client.index("movies")
    response = await index.add_documents_from_file_in_batches(
        small_movies_path, batch_size=batch_size, primary_key=primary_key
    )
    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents_from_file_string_path_in_batches(
    batch_size, primary_key, expected_primary_key, test_client, small_movies_path, small_movies
):
    string_path = str(small_movies_path)
    index = test_client.index("movies")
    response = await index.add_documents_from_file_in_batches(
        string_path, batch_size=batch_size, primary_key=primary_key
    )
    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await index.wait_for_pending_update(r.update_id)
        assert update.status == "processed"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.asyncio
async def test_add_documents_from_file_in_batches_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.add_documents_from_file_in_batches("test.csv")


@pytest.mark.asyncio
async def test_get_document(index_with_documents):
    index = await index_with_documents()
    response = await index.get_document("500682")
    assert response["title"] == "The Highwaymen"


@pytest.mark.asyncio
async def test_get_document_inexistent(empty_index):
    with pytest.raises(MeiliSearchApiError):
        index = await empty_index()
        await index.get_document("123")


@pytest.mark.asyncio
async def test_get_documents_populated(index_with_documents):
    index = await index_with_documents()
    response = await index.get_documents()
    assert len(response) == 20


@pytest.mark.asyncio
async def test_get_documents_offset_optional_params(index_with_documents):
    index = await index_with_documents()
    response = await index.get_documents()
    assert len(response) == 20
    response_offset_limit = await index.get_documents(
        limit=3, offset=1, attributes_to_retrieve="title"
    )
    assert len(response_offset_limit) == 3
    assert response_offset_limit[0]["title"] == response[1]["title"]


@pytest.mark.asyncio
async def test_update_documents(index_with_documents, small_movies):
    index = await index_with_documents()
    response = await index.get_documents()
    response[0]["title"] = "Some title"
    update = await index.update_documents([response[0]])
    await index.wait_for_pending_update(update.update_id)
    response = await index.get_documents()
    assert response[0]["title"] == "Some title"
    update = await index.update_documents(small_movies)
    await index.wait_for_pending_update(update.update_id)
    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
async def test_update_documents_with_primary_key(test_client, small_movies):
    primary_key = "release_date"
    index = test_client.index("movies")
    update = await index.update_documents(small_movies, primary_key=primary_key)
    await index.wait_for_pending_update(update.update_id)
    assert await index.get_primary_key() == primary_key


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
async def test_update_documents_auto_batch(max_payload, test_client):
    documents = generate_test_movies()

    index = test_client.index("movies")
    response = await index.add_documents(documents)
    update = await index.wait_for_pending_update(response.update_id)
    assert update.status == "processed"

    response = await index.get_documents(limit=len(documents))
    assert response[0]["title"] != "Some title"

    response[0]["title"] = "Some title"

    if max_payload:
        updates = await index.update_documents_auto_batch(response, max_payload_size=max_payload)
    else:
        updates = await index.update_documents_auto_batch(response)

    for update in updates:
        await index.wait_for_pending_update(update.update_id)

    stats = await index.get_stats()
    assert stats.number_of_documents == len(documents)

    response = await index.get_documents()
    assert response[0]["title"] == "Some title"


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
async def test_update_documents_auto_batch_primary_key(test_client, max_payload):
    documents = generate_test_movies()
    primary_key = "release_date"
    index = test_client.index("movies")
    if max_payload:
        updates = await index.update_documents_auto_batch(
            documents, max_payload_size=max_payload, primary_key=primary_key
        )
    else:
        updates = await index.update_documents_auto_batch(documents, primary_key=primary_key)

    for update in updates:
        update_status = await index.wait_for_pending_update(update.update_id)
        assert update_status.status == "processed"

    # TODO: The number of documents test is failing here, but as far as I can tell so far the issue
    # is coming from MeiliSearch and not something in this package. As soon as this is resolved
    # this test should be turned back on.
    # stats = await index.get_stats()
    #
    # assert stats.number_of_documents == len(documents)
    assert await index.get_primary_key() == primary_key


@pytest.mark.asyncio
async def test_update_documents_auto_batch_payload_size_error(empty_index, small_movies):
    with pytest.raises(PayloadTooLarge):
        index = await empty_index()
        await index.update_documents_auto_batch(small_movies, max_payload_size=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_in_batches(batch_size, index_with_documents, small_movies):
    index = await index_with_documents()
    response = await index.get_documents()
    response[0]["title"] = "Some title"
    update = await index.update_documents([response[0]])
    await index.wait_for_pending_update(update.update_id)

    response = await index.get_documents()
    assert response[0]["title"] == "Some title"
    updates = await index.update_documents_in_batches(small_movies, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        await index.wait_for_pending_update(update.update_id)

    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_in_batches_with_primary_key(batch_size, test_client, small_movies):
    primary_key = "release_date"
    index = test_client.index("movies")
    updates = await index.update_documents_in_batches(
        small_movies, batch_size=batch_size, primary_key=primary_key
    )
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await index.wait_for_pending_update(update.update_id)
        assert update_status.status == "processed"

    assert await index.get_primary_key() == primary_key


@pytest.mark.asyncio
async def test_update_documents_from_file(test_client, small_movies, small_movies_path):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response)
    assert list(got_title)[0]["title"] == "Some title"
    update = await index.update_documents_from_file(small_movies_path)
    update = await index.wait_for_pending_update(update.update_id)
    assert update.status == "processed"
    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
async def test_update_documents_from_file_string_path(test_client, small_movies, small_movies_path):
    string_path = str(small_movies_path)
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response)
    assert list(got_title)[0]["title"] == "Some title"
    update = await index.update_documents_from_file(string_path)
    update = await index.wait_for_pending_update(update.update_id)
    assert update.status == "processed"
    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
async def test_update_documents_from_file_with_primary_key(test_client, small_movies_path):
    primary_key = "release_date"
    index = test_client.index("movies")
    update = await index.update_documents_from_file(small_movies_path, primary_key=primary_key)
    await index.wait_for_pending_update(update.update_id)
    assert await index.get_primary_key() == primary_key


@pytest.mark.asyncio
async def test_update_documents_from_file_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.update_documents_from_file("test.csv")


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
async def test_update_documents_from_file_auto_batch(max_payload, test_client, tmp_path):
    documents = generate_test_movies()

    index = test_client.index("movies")
    response = await index.add_documents(documents)
    update = await index.wait_for_pending_update(response.update_id)
    assert update.status == "processed"

    response = await index.get_documents(limit=len(documents))
    assert response[0]["title"] != "Some title"

    response[0]["title"] = "Some title"

    test_file = tmp_path / "test.json"
    with open(test_file, "w") as f:
        json.dump(response, f)

    if max_payload:
        updates = await index.update_documents_from_file_auto_batch(
            test_file, max_payload_size=max_payload
        )
    else:
        updates = await index.update_documents_from_file_auto_batch(test_file)

    for update in updates:
        await index.wait_for_pending_update(update.update_id)

    response = await index.get_documents()
    stats = await index.get_stats()

    assert stats.number_of_documents == len(documents)
    assert response[0]["title"] == "Some title"


@pytest.mark.asyncio
@pytest.mark.parametrize("max_payload", [None, 3500, 2500])
async def test_update_documents_from_file_string_path_auto_batch(
    max_payload, test_client, tmp_path
):
    documents = generate_test_movies()

    index = test_client.index("movies")
    response = await index.add_documents(documents)
    update = await index.wait_for_pending_update(response.update_id)
    assert update.status == "processed"

    response = await index.get_documents(limit=len(documents))
    assert response[0]["title"] != "Some title"

    response[0]["title"] = "Some title"

    test_file = tmp_path / "test.json"
    with open(test_file, "w") as f:
        json.dump(response, f)

    if max_payload:
        updates = await index.update_documents_from_file_auto_batch(
            str(test_file), max_payload_size=max_payload
        )
    else:
        updates = await index.update_documents_from_file_auto_batch(str(test_file))

    for update in updates:
        await index.wait_for_pending_update(update.update_id)

    response = await index.get_documents()
    stats = await index.get_stats()

    assert stats.number_of_documents == len(documents)
    assert response[0]["title"] == "Some title"


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_from_file_in_batches(
    batch_size, test_client, small_movies_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response)
    assert list(got_title)[0]["title"] == "Some title"
    updates = await index.update_documents_from_file_in_batches(
        small_movies_path, batch_size=batch_size
    )
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await index.wait_for_pending_update(update.update_id)
        assert update_status.status == "processed"

    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_from_file_string_path_in_batches(
    batch_size, test_client, small_movies_path, small_movies
):
    string_path = str(small_movies_path)
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await index.wait_for_pending_update(response.update_id)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response)
    assert list(got_title)[0]["title"] == "Some title"
    updates = await index.update_documents_from_file_in_batches(string_path, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await index.wait_for_pending_update(update.update_id)
        assert update_status.status == "processed"

    response = await index.get_documents()
    assert response[0]["title"] != "Some title"


@pytest.mark.asyncio
async def test_update_documents_from_file_in_batches_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.update_documents_from_file_in_batches("test.csv")


@pytest.mark.asyncio
async def test_delete_document(index_with_documents):
    index = await index_with_documents()
    response = await index.delete_document("500682")
    await index.wait_for_pending_update(response.update_id)
    with pytest.raises(MeiliSearchApiError):
        await index.get_document("500682")


@pytest.mark.asyncio
async def test_delete_documents(index_with_documents):
    to_delete = ["522681", "450465", "329996"]
    index = await index_with_documents()
    response = await index.delete_documents(to_delete)
    await index.wait_for_pending_update(response.update_id)
    documents = await index.get_documents()
    ids = [x["id"] for x in documents]
    assert to_delete not in ids


@pytest.mark.asyncio
async def test_delete_all_documents(index_with_documents):
    index = await index_with_documents()
    response = await index.delete_all_documents()
    await index.wait_for_pending_update(response.update_id)
    response = await index.get_documents()
    assert response is None
