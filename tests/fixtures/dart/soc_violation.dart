// REASSURE: expect soc_violation (Widget + Repository archetypes co-located)
// REASSURE: expect soc_violation (imports: dio, sqflite in a views/ file)
// REASSURE: expect soc_violation (class name UserRepository in a views/ context)
//
// A widget file that also owns its data fetching.
// Common in early-stage Flutter apps. Always regretted.

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:sqflite/sqflite.dart';

// Data model crammed into the view file
class User {
  final String id;
  final String name;

  User({required this.id, required this.name});

  factory User.fromJson(Map<String, dynamic> json) =>
      User(id: json['id'] as String, name: json['name'] as String);
}

// Repository crammed into the view file
// REASSURE: expect soc_violation (class UserRepository in file path containing 'view' or 'screen')
class UserRepository {
  final Dio _dio;
  final Database _db;

  UserRepository(this._dio, this._db);

  Future<User?> fetchUser(String id) async {
    final response = await _dio.get('/users/$id');
    return User.fromJson(response.data as Map<String, dynamic>);
  }

  Future<void> cacheUser(User user) async {
    await _db.insert('users', {'id': user.id, 'name': user.name},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }
}

// The actual widget — mixed with everything above
class UserProfileView extends StatefulWidget {
  final String userId;

  const UserProfileView({super.key, required this.userId});

  @override
  State<UserProfileView> createState() => _UserProfileViewState();
}

class _UserProfileViewState extends State<UserProfileView> {
  User? _user;
  bool _loading = false;

  // Instantiating dependencies inline in the widget — no DI, no separation
  final _repo = UserRepository(Dio(), throw UnimplementedError());

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    _user = await _repo.fetchUser(widget.userId);
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const CircularProgressIndicator();
    if (_user == null) return const Text('Not found');
    return Text(_user!.name);
  }
}
