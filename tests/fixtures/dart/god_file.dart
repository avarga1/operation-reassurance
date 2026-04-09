// REASSURE: expect god_file (LOC > 500, classes > 5, methods > 20)
// REASSURE: expect god_class DashboardShell (methods > 15)
//
// This file is intentionally terrible.
// It exists to prove the SOLID analyzer catches it.
// Do not use as a template for anything.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart';

// ── Data models (should be in models/) ───────────────────────────────────────

class UserProfile {
  final String id;
  final String name;
  final String email;
  final DateTime createdAt;
  final Map<String, dynamic> metadata;

  UserProfile({
    required this.id,
    required this.name,
    required this.email,
    required this.createdAt,
    required this.metadata,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as String,
      name: json['name'] as String,
      email: json['email'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      metadata: json['metadata'] as Map<String, dynamic>? ?? {},
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'email': email,
        'created_at': createdAt.toIso8601String(),
        'metadata': metadata,
      };
}

class ActivityRecord {
  final String id;
  final String userId;
  final String type;
  final double value;
  final DateTime timestamp;

  ActivityRecord({
    required this.id,
    required this.userId,
    required this.type,
    required this.value,
    required this.timestamp,
  });

  factory ActivityRecord.fromJson(Map<String, dynamic> json) {
    return ActivityRecord(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      type: json['type'] as String,
      value: (json['value'] as num).toDouble(),
      timestamp: DateTime.parse(json['timestamp'] as String),
    );
  }
}

// ── Repository (should be in repositories/) ──────────────────────────────────

class UserRepository {
  final Database _db;
  final Dio _dio;

  UserRepository(this._db, this._dio);

  Future<UserProfile?> getById(String id) async {
    final rows = await _db.query('users', where: 'id = ?', whereArgs: [id]);
    if (rows.isEmpty) return null;
    return UserProfile.fromJson(rows.first);
  }

  Future<void> save(UserProfile profile) async {
    await _db.insert(
      'users',
      profile.toJson(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> delete(String id) async {
    await _db.delete('users', where: 'id = ?', whereArgs: [id]);
  }

  Future<List<UserProfile>> fetchAllFromApi() async {
    final response = await _dio.get('/users');
    final list = response.data as List<dynamic>;
    return list.map((e) => UserProfile.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> syncToRemote(UserProfile profile) async {
    await _dio.put('/users/${profile.id}', data: profile.toJson());
  }
}

class ActivityRepository {
  final Database _db;

  ActivityRepository(this._db);

  Future<List<ActivityRecord>> getForUser(String userId) async {
    final rows = await _db.query(
      'activities',
      where: 'user_id = ?',
      whereArgs: [userId],
      orderBy: 'timestamp DESC',
    );
    return rows.map((r) => ActivityRecord.fromJson(r)).toList();
  }

  Future<void> insert(ActivityRecord record) async {
    await _db.insert('activities', {
      'id': record.id,
      'user_id': record.userId,
      'type': record.type,
      'value': record.value,
      'timestamp': record.timestamp.toIso8601String(),
    });
  }

  Future<void> purgeOlderThan(DateTime cutoff) async {
    await _db.delete(
      'activities',
      where: 'timestamp < ?',
      whereArgs: [cutoff.toIso8601String()],
    );
  }
}

// ── Service (should be in services/) ─────────────────────────────────────────

class AuthService {
  final Dio _dio;
  String? _token;

  AuthService(this._dio);

  Future<bool> login(String email, String password) async {
    try {
      final response = await _dio.post('/auth/login', data: {
        'email': email,
        'password': password,
      });
      _token = response.data['token'] as String?;
      return _token != null;
    } on DioException {
      return false;
    }
  }

  Future<void> logout() async {
    await _dio.post('/auth/logout');
    _token = null;
  }

  bool get isAuthenticated => _token != null;

  String? get token => _token;
}

// ── The actual god shell widget ───────────────────────────────────────────────

// REASSURE: expect god_class DashboardShell (methods > 15, mixes UI + data + network)
class DashboardShell extends StatefulWidget {
  final String userId;

  const DashboardShell({super.key, required this.userId});

  @override
  State<DashboardShell> createState() => _DashboardShellState();
}

class _DashboardShellState extends State<DashboardShell>
    with TickerProviderStateMixin {
  late final Dio _dio;
  late final Database _db;
  late final UserRepository _userRepo;
  late final ActivityRepository _activityRepo;
  late final AuthService _authService;
  late final AnimationController _fadeController;
  late final AnimationController _slideController;

  UserProfile? _profile;
  List<ActivityRecord> _activities = [];
  bool _isLoading = false;
  bool _isSyncing = false;
  String? _error;
  int _selectedTab = 0;
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  Timer? _syncTimer;

  @override
  void initState() {
    super.initState();
    _dio = Dio(BaseOptions(baseUrl: 'https://api.example.com'));
    _db = await _openDatabase();
    _userRepo = UserRepository(_db, _dio);
    _activityRepo = ActivityRepository(_db);
    _authService = AuthService(_dio);
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slideController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    _startSyncTimer();
    _loadData();
  }

  Future<Database> _openDatabase() async {
    return openDatabase(
      'dashboard.db',
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            created_at TEXT,
            metadata TEXT
          )
        ''');
        await db.execute('''
          CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            type TEXT,
            value REAL,
            timestamp TEXT
          )
        ''');
      },
    );
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    try {
      _profile = await _userRepo.getById(widget.userId);
      if (_profile == null) {
        await _syncFromApi();
      }
      _activities = await _activityRepo.getForUser(widget.userId);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _syncFromApi() async {
    setState(() => _isSyncing = true);
    try {
      final profiles = await _userRepo.fetchAllFromApi();
      for (final p in profiles) {
        await _userRepo.save(p);
      }
      _profile = await _userRepo.getById(widget.userId);
    } catch (e) {
      setState(() => _error = 'Sync failed: $e');
    } finally {
      setState(() => _isSyncing = false);
    }
  }

  void _startSyncTimer() {
    _syncTimer = Timer.periodic(const Duration(minutes: 5), (_) => _syncFromApi());
  }

  Future<void> _handleLogout() async {
    await _authService.logout();
    if (mounted) Navigator.of(context).pushReplacementNamed('/login');
  }

  void _handleTabChange(int index) {
    setState(() => _selectedTab = index);
    if (index == 0) {
      _fadeController.forward();
      _slideController.reverse();
    } else {
      _fadeController.reverse();
      _slideController.forward();
    }
  }

  List<ActivityRecord> _filteredActivities() {
    final query = _searchController.text.toLowerCase();
    if (query.isEmpty) return _activities;
    return _activities.where((a) => a.type.toLowerCase().contains(query)).toList();
  }

  double _totalValue(String type) {
    return _activities
        .where((a) => a.type == type)
        .fold(0.0, (sum, a) => sum + a.value);
  }

  Map<String, double> _activitySummary() {
    final summary = <String, double>{};
    for (final a in _activities) {
      summary[a.type] = (summary[a.type] ?? 0) + a.value;
    }
    return summary;
  }

  Future<void> _exportToFile() async {
    final data = {
      'profile': _profile?.toJson(),
      'activities': _activities.map((a) => {
        'id': a.id,
        'type': a.type,
        'value': a.value,
        'timestamp': a.timestamp.toIso8601String(),
      }).toList(),
    };
    final json = jsonEncode(data);
    final dir = await getApplicationDocumentsDirectory();
    final file = File('${dir.path}/export_${DateTime.now().millisecondsSinceEpoch}.json');
    await file.writeAsString(json);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Exported to ${file.path}')),
      );
    }
  }

  Future<void> _purgeOldData() async {
    final cutoff = DateTime.now().subtract(const Duration(days: 90));
    await _activityRepo.purgeOlderThan(cutoff);
    await _loadData();
  }

  void _scrollToTop() {
    _scrollController.animateTo(
      0,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
    );
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    _fadeController.dispose();
    _slideController.dispose();
    _searchController.dispose();
    _scrollController.dispose();
    _db.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        body: Center(child: Text(_error!, style: const TextStyle(color: Colors.red))),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(_profile?.name ?? 'Dashboard'),
        actions: [
          if (_isSyncing) const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
          IconButton(icon: const Icon(Icons.sync), onPressed: _syncFromApi),
          IconButton(icon: const Icon(Icons.download), onPressed: _exportToFile),
          IconButton(icon: const Icon(Icons.logout), onPressed: _handleLogout),
        ],
      ),
      body: Column(
        children: [
          TextField(
            controller: _searchController,
            decoration: const InputDecoration(hintText: 'Search activities...'),
            onChanged: (_) => setState(() {}),
          ),
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              itemCount: _filteredActivities().length,
              itemBuilder: (context, index) {
                final activity = _filteredActivities()[index];
                return ListTile(
                  title: Text(activity.type),
                  subtitle: Text(activity.timestamp.toString()),
                  trailing: Text(activity.value.toStringAsFixed(1)),
                );
              },
            ),
          ),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedTab,
        onTap: _handleTabChange,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.bar_chart), label: 'Stats'),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _scrollToTop,
        child: const Icon(Icons.arrow_upward),
      ),
    );
  }
}

// ── Utility widget (fine on its own, not fine living here) ───────────────────

class ActivityTile extends StatelessWidget {
  final ActivityRecord activity;

  const ActivityTile({super.key, required this.activity});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(activity.type),
        subtitle: Text(activity.timestamp.toLocal().toString()),
        trailing: Text('${activity.value.toStringAsFixed(1)}'),
      ),
    );
  }
}

// helper that has no business being here
Future<Directory> getApplicationDocumentsDirectory() async {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final path = await channel.invokeMethod<String>('getApplicationDocumentsDirectory');
  return Directory(path!);
}
