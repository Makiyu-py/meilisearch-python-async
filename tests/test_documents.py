import csv
import json
from math import ceil

import pytest

from meilisearch_python_async.errors import (
    InvalidDocumentError,
    MeiliSearchApiError,
    MeiliSearchError,
)
from meilisearch_python_async.index import _combine_documents, _load_documents_from_file
from meilisearch_python_async.task import wait_for_task


def generate_test_movies(num_movies=50, id_start=0):
    movies = []
    # Each moves is ~ 174 bytes
    for i in range(num_movies):
        movie = {
            "id": i + id_start,
            "title": "test",
            "poster": "test",
            "overview": "test",
            "release_date": 1551830399,
            "pk_test": i + id_start + 1,
            "genre": "test",
        }
        movies.append(movie)

    return movies


def add_json_file(file_path, num_movies=50, id_start=0):
    with open(file_path, "w") as f:
        json.dump(generate_test_movies(num_movies, id_start), f)


def add_csv_file(file_path, num_movies=50, id_start=0):
    with open(file_path, "w") as f:
        movies = generate_test_movies(num_movies, id_start)
        field_names = list(movies[0].keys())
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(movies)


def add_ndjson_file(file_path, num_movies=50, id_start=0):
    movies = [json.dumps(x) for x in generate_test_movies(num_movies, id_start)]
    with open(file_path, "w") as f:
        for line in movies:
            f.write(f"{line}\n")


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


async def test_get_documents_default(empty_index):
    index = await empty_index()
    response = await index.get_documents()
    assert response.results == []


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
async def test_add_documents(primary_key, expected_primary_key, empty_index, small_movies):
    index = await empty_index()
    response = await index.add_documents(small_movies, primary_key)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


@pytest.mark.parametrize("batch_size", [2, 3])
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
        update = await wait_for_task(index.http_client, r.task_uid)
        assert update.status == "succeeded"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
@pytest.mark.parametrize(
    "number_of_files, documents_per_file, total_documents", [(1, 50, 50), (2, 50, 100)]
)
async def test_add_documents_from_directory(
    path_type,
    combine_documents,
    number_of_files,
    documents_per_file,
    total_documents,
    test_client,
    tmp_path,
):
    for i in range(number_of_files):
        add_json_file(tmp_path / f"test{i}.json", documents_per_file, i * documents_per_file)

    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory(path, combine_documents=combine_documents)
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == total_documents


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_add_documents_from_directory_csv_path(
    path_type, combine_documents, test_client, tmp_path
):
    add_csv_file(tmp_path / "test1.csv", 50, 0)
    add_csv_file(tmp_path / "test2.csv", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory(
        path, combine_documents=combine_documents, document_type="csv"
    )
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_add_documents_from_directory_ndjson(
    path_type, combine_documents, test_client, tmp_path
):
    add_ndjson_file(tmp_path / "test1.ndjson", 50, 0)
    add_ndjson_file(tmp_path / "test2.ndjson", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory(
        path, combine_documents=combine_documents, document_type="ndjson"
    )
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("combine_documents", [True, False])
async def test_add_documents_from_directory_no_documents(combine_documents, test_client, tmp_path):
    with open(tmp_path / "test.txt", "w") as f:
        f.write("nothing")

    with pytest.raises(MeiliSearchError):
        index = test_client.index("movies")
        await index.add_documents_from_directory(tmp_path, combine_documents=combine_documents)


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
@pytest.mark.parametrize(
    "number_of_files, documents_per_file, total_documents", [(1, 50, 50), (2, 50, 100)]
)
async def test_add_documents_from_directory_in_batchs(
    path_type,
    combine_documents,
    batch_size,
    number_of_files,
    documents_per_file,
    total_documents,
    test_client,
    tmp_path,
):
    for i in range(number_of_files):
        add_json_file(tmp_path / f"test{i}.json", documents_per_file, i * documents_per_file)

    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == total_documents


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_add_documents_from_directory_in_batchs_csv(
    path_type, combine_documents, batch_size, test_client, tmp_path
):
    add_csv_file(tmp_path / "test1.csv", 50, 0)
    add_csv_file(tmp_path / "test2.csv", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents, document_type="csv"
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_add_documents_from_directory_in_batchs_ndjson(
    path_type, combine_documents, batch_size, test_client, tmp_path
):
    add_ndjson_file(tmp_path / "test1.ndjson", 50, 0)
    add_ndjson_file(tmp_path / "test2.ndjson", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.add_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents, document_type="ndjson"
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file(
    path_type, primary_key, expected_primary_key, test_client, small_movies_path
):
    index = test_client.index("movies")
    path = str(small_movies_path) if path_type == "str" else small_movies_path
    response = await index.add_documents_from_file(path, primary_key)

    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file_csv(
    path_type, primary_key, expected_primary_key, test_client, small_movies_csv_path
):
    index = test_client.index("movies")
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    response = await index.add_documents_from_file(path, primary_key)

    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_raw_file_csv(
    path_type, primary_key, expected_primary_key, test_client, small_movies_csv_path
):
    index = test_client.index("movies")
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    response = await index.add_documents_from_raw_file(path, primary_key)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_raw_file_ndjson(
    path_type, primary_key, expected_primary_key, test_client, small_movies_ndjson_path
):
    index = test_client.index("movies")
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    response = await index.add_documents_from_raw_file(path, primary_key)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


async def test_add_documents_raw_file_not_found_error(test_client, tmp_path):
    with pytest.raises(MeiliSearchError):
        index = test_client.index("movies")
        await index.add_documents_from_raw_file(tmp_path / "file.csv")


async def test_add_document_raw_file_extension_error(test_client, tmp_path):
    file_path = tmp_path / "file.bad"
    with open(file_path, "w") as f:
        f.write("test")

    with pytest.raises(ValueError):
        index = test_client.index("movies")
        await index.add_documents_from_raw_file(file_path)


@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file_ndjson(
    path_type, primary_key, expected_primary_key, test_client, small_movies_ndjson_path
):
    index = test_client.index("movies")
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    response = await index.add_documents_from_file(path, primary_key)

    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == expected_primary_key
    assert update.status == "succeeded"


async def test_add_documents_from_file_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.add_documents_from_file("test.bad")


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file_in_batches(
    path_type,
    batch_size,
    primary_key,
    expected_primary_key,
    test_client,
    small_movies_path,
    small_movies,
):
    index = test_client.index("movies")
    path = str(small_movies_path) if path_type == "str" else small_movies_path
    response = await index.add_documents_from_file_in_batches(
        path, batch_size=batch_size, primary_key=primary_key
    )

    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await wait_for_task(index.http_client, r.task_uid)
        assert update.status == "succeeded"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file_in_batches_csv(
    path_type,
    batch_size,
    primary_key,
    expected_primary_key,
    test_client,
    small_movies_csv_path,
    small_movies,
):
    index = test_client.index("movies")
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    response = await index.add_documents_from_file_in_batches(
        path, batch_size=batch_size, primary_key=primary_key
    )

    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await wait_for_task(index.http_client, r.task_uid)
        assert update.status == "succeeded"

    assert await index.get_primary_key() == expected_primary_key


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize(
    "primary_key, expected_primary_key", [("release_date", "release_date"), (None, "id")]
)
@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_add_documents_from_file_in_batches_ndjson(
    path_type,
    batch_size,
    primary_key,
    expected_primary_key,
    test_client,
    small_movies_ndjson_path,
    small_movies,
):
    index = test_client.index("movies")
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    response = await index.add_documents_from_file_in_batches(
        path, batch_size=batch_size, primary_key=primary_key
    )

    assert ceil(len(small_movies) / batch_size) == len(response)

    for r in response:
        update = await wait_for_task(index.http_client, r.task_uid)
        assert update.status == "succeeded"

    assert await index.get_primary_key() == expected_primary_key


async def test_add_documents_from_file_in_batches_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.add_documents_from_file_in_batches("test.bad")


async def test_get_document(index_with_documents):
    index = await index_with_documents()
    response = await index.get_document("500682")
    assert response["title"] == "The Highwaymen"


async def test_get_document_inexistent(empty_index):
    with pytest.raises(MeiliSearchApiError):
        index = await empty_index()
        await index.get_document("123")


async def test_get_documents_populated(index_with_documents):
    index = await index_with_documents()
    response = await index.get_documents()
    assert len(response.results) == 20


async def test_get_documents_offset_optional_params(index_with_documents):
    index = await index_with_documents()
    response = await index.get_documents()
    assert len(response.results) == 20
    response_offset_limit = await index.get_documents(
        limit=3, offset=1, fields=["title", "overview"]
    )
    assert len(response_offset_limit.results) == 3
    assert response_offset_limit.results[0]["title"] == response.results[1]["title"]
    assert response_offset_limit.results[0]["overview"] == response.results[1]["overview"]


async def test_update_documents(index_with_documents, small_movies):
    index = await index_with_documents()
    response = await index.get_documents()
    doc_id = response.results[0]["id"]
    response.results[0]["title"] = "Some title"
    update = await index.update_documents([response.results[0]])
    await wait_for_task(index.http_client, update.task_uid)
    response = await index.get_document(doc_id)
    assert response["title"] == "Some title"
    update = await index.update_documents(small_movies)
    await wait_for_task(index.http_client, update.task_uid)
    response = await index.get_document(doc_id)
    assert response["title"] != "Some title"


async def test_update_documents_with_primary_key(test_client, small_movies):
    primary_key = "release_date"
    index = test_client.index("movies")
    update = await index.update_documents(small_movies, primary_key=primary_key)
    await wait_for_task(index.http_client, update.task_uid)
    assert await index.get_primary_key() == primary_key


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_in_batches(batch_size, index_with_documents, small_movies):
    index = await index_with_documents()
    response = await index.get_documents()
    doc_id = response.results[0]["id"]
    response.results[0]["title"] = "Some title"
    update = await index.update_documents([response.results[0]])
    await wait_for_task(index.http_client, update.task_uid)

    response = await index.get_document(doc_id)
    assert response["title"] == "Some title"
    updates = await index.update_documents_in_batches(small_movies, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        await wait_for_task(index.http_client, update.task_uid)

    response = await index.get_document(doc_id)
    assert response["title"] != "Some title"


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_in_batches_with_primary_key(batch_size, test_client, small_movies):
    primary_key = "release_date"
    index = test_client.index("movies")
    updates = await index.update_documents_in_batches(
        small_movies, batch_size=batch_size, primary_key=primary_key
    )
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await wait_for_task(index.http_client, update.task_uid)
        assert update_status.status == "succeeded"

    assert await index.get_primary_key() == primary_key


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
@pytest.mark.parametrize(
    "number_of_files, documents_per_file, total_documents", [(1, 50, 50), (10, 50, 500)]
)
async def test_update_documents_from_directory(
    path_type,
    combine_documents,
    number_of_files,
    documents_per_file,
    total_documents,
    test_client,
    tmp_path,
):
    for i in range(number_of_files):
        add_json_file(tmp_path / f"test{i}.json", documents_per_file, i * documents_per_file)

    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory(
        path, combine_documents=combine_documents
    )
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == total_documents


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_update_documents_from_directory_csv(
    path_type, combine_documents, test_client, tmp_path
):
    add_csv_file(tmp_path / "test1.csv", 50, 0)
    add_csv_file(tmp_path / "test2.csv", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory(
        path, combine_documents=combine_documents, document_type="csv"
    )
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_update_documents_from_directory_ndjson(
    path_type, combine_documents, test_client, tmp_path
):
    add_ndjson_file(tmp_path / "test1.ndjson", 50, 0)
    add_ndjson_file(tmp_path / "test2.ndjson", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory(
        path, combine_documents=combine_documents, document_type="ndjson"
    )
    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
@pytest.mark.parametrize(
    "number_of_files, documents_per_file, total_documents", [(1, 50, 50), (2, 50, 100)]
)
async def test_update_documents_from_directory_in_batchs(
    path_type,
    combine_documents,
    batch_size,
    number_of_files,
    documents_per_file,
    total_documents,
    test_client,
    tmp_path,
):
    for i in range(number_of_files):
        add_json_file(tmp_path / f"text{i}.json", documents_per_file, i * documents_per_file)

    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == total_documents


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_update_documents_from_directory_in_batchs_csv(
    path_type, combine_documents, batch_size, test_client, tmp_path
):
    add_csv_file(tmp_path / "test1.csv", 50, 0)
    add_csv_file(tmp_path / "test2.csv", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents, document_type="csv"
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("batch_size", [2, 3, 1000])
@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("combine_documents", [True, False])
async def test_update_documents_from_directory_in_batchs_ndjson(
    path_type, combine_documents, batch_size, test_client, tmp_path
):
    add_ndjson_file(tmp_path / "test1.ndjson", 50, 0)
    add_ndjson_file(tmp_path / "test2.ndjson", 50, 51)
    index = test_client.index("movies")
    path = str(tmp_path) if path_type == "str" else tmp_path
    responses = await index.update_documents_from_directory_in_batches(
        path, batch_size=batch_size, combine_documents=combine_documents, document_type="ndjson"
    )

    for response in responses:
        await wait_for_task(index.http_client, response.task_uid)
    stats = await index.get_stats()
    assert stats.number_of_documents == 100


@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_update_documents_from_file(path_type, test_client, small_movies, small_movies_path):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_path) if path_type == "str" else small_movies_path
    update = await index.update_documents_from_file(path)
    update = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
    assert update.status == "succeeded"
    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_update_documents_from_file_csv(
    path_type, test_client, small_movies, small_movies_csv_path
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    update = await index.update_documents_from_file(path)
    update = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
    assert update.status == "succeeded"
    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_update_documents_from_file_ndjson(
    path_type, test_client, small_movies, small_movies_ndjson_path
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    update = await index.update_documents_from_file(path)
    update = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
    assert update.status == "succeeded"
    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


async def test_update_documents_from_file_with_primary_key(test_client, small_movies_path):
    primary_key = "release_date"
    index = test_client.index("movies")
    update = await index.update_documents_from_file(small_movies_path, primary_key=primary_key)
    await wait_for_task(index.http_client, update.task_uid)
    assert await index.get_primary_key() == primary_key


async def test_update_documents_from_file_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.update_documents_from_file("test.bad")


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_from_file_in_batches(
    path_type, batch_size, test_client, small_movies_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_path) if path_type == "str" else small_movies_path
    updates = await index.update_documents_from_file_in_batches(path, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
        assert update_status.status == "succeeded"

    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_from_file_in_batches_csv(
    path_type, batch_size, test_client, small_movies_csv_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    updates = await index.update_documents_from_file_in_batches(path, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
        assert update_status.status == "succeeded"

    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


@pytest.mark.parametrize("path_type", ["path", "str"])
@pytest.mark.parametrize("batch_size", [2, 3, 1000])
async def test_update_documents_from_file_in_batches_ndjson(
    path_type, batch_size, test_client, small_movies_ndjson_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    updates = await index.update_documents_from_file_in_batches(path, batch_size=batch_size)
    assert ceil(len(small_movies) / batch_size) == len(updates)

    for update in updates:
        update_status = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
        assert update_status.status == "succeeded"

    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


async def test_update_documents_from_file_in_batches_invalid_extension(test_client):
    index = test_client.index("movies")

    with pytest.raises(MeiliSearchError):
        await index.update_documents_from_file_in_batches("test.bad")


@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_update_documents_raw_file_csv(
    path_type, test_client, small_movies_csv_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_csv_path) if path_type == "str" else small_movies_csv_path
    update = await index.update_documents_from_raw_file(path, primary_key="id")
    update = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
    assert update.status == "succeeded"
    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


@pytest.mark.parametrize("path_type", ["path", "str"])
async def test_update_documents_raw_file_ndjson(
    path_type, test_client, small_movies_ndjson_path, small_movies
):
    small_movies[0]["title"] = "Some title"
    movie_id = small_movies[0]["id"]
    index = test_client.index("movies")
    response = await index.add_documents(small_movies)
    update = await wait_for_task(index.http_client, response.task_uid)
    assert await index.get_primary_key() == "id"
    response = await index.get_documents()
    got_title = filter(lambda x: x["id"] == movie_id, response.results)
    assert list(got_title)[0]["title"] == "Some title"
    path = str(small_movies_ndjson_path) if path_type == "str" else small_movies_ndjson_path
    update = await index.update_documents_from_raw_file(path)
    update = await wait_for_task(index.http_client, update.task_uid)  # type: ignore
    assert update.status == "succeeded"
    response = await index.get_documents()
    assert response.results[0]["title"] != "Some title"


async def test_update_documents_raw_file_not_found_error(test_client, tmp_path):
    with pytest.raises(MeiliSearchError):
        index = test_client.index("movies")
        await index.update_documents_from_raw_file(tmp_path / "file.csv")


async def test_update_document_raw_file_extension_error(test_client, tmp_path):
    file_path = tmp_path / "file.bad"
    with open(file_path, "w") as f:
        f.write("test")

    with pytest.raises(ValueError):
        index = test_client.index("movies")
        await index.update_documents_from_raw_file(file_path)


async def test_delete_document(index_with_documents):
    index = await index_with_documents()
    response = await index.delete_document("500682")
    await wait_for_task(index.http_client, response.task_uid)
    with pytest.raises(MeiliSearchApiError):
        await index.get_document("500682")


async def test_delete_documents(index_with_documents):
    to_delete = ["522681", "450465", "329996"]
    index = await index_with_documents()
    response = await index.delete_documents(to_delete)
    await wait_for_task(index.http_client, response.task_uid)
    documents = await index.get_documents()
    ids = [x["id"] for x in documents.results]
    assert to_delete not in ids


async def test_delete_all_documents(index_with_documents):
    index = await index_with_documents()
    response = await index.delete_all_documents()
    await wait_for_task(index.http_client, response.task_uid)
    response = await index.get_documents()
    assert response.results == []


async def test_load_documents_from_file_invalid_document(tmp_path):
    doc = {"id": 1, "name": "test"}
    file_path = tmp_path / "test.json"
    with open(file_path, "w") as f:
        json.dump(doc, f)

    with pytest.raises(InvalidDocumentError):
        await _load_documents_from_file(file_path)


def test_combine_documents():
    docs = [
        [{"id": 1, "name": "Test 1"}, {"id": 2, "name": "Test 2"}],
        [{"id": 3, "name": "Test 3"}],
    ]

    combined = _combine_documents(docs)

    assert len(combined) == 3
    assert [1, 2, 3] == [x["id"] for x in combined]
